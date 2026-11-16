"""Run a live chat-spike clipper against an authorised media URL.

This script does not resolve Twitch channel pages or download third-party VODs.
Set LIVE_VIDEO_URL to a direct media input you own or are explicitly authorised
to record. The URL is not printed by the application.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

from gta_researcher.live_clips import (
    ChatSpikeDetector,
    SegmentRecorder,
    SpikeConfig,
    save_spike_metadata,
)
from gta_researcher.twitch_chat import TwitchIRCReader

try:
    from transcribe_clips import transcribe_file
except ImportError:
    transcribe_file = None


async def run(args: argparse.Namespace) -> None:
    source_url = os.getenv("LIVE_VIDEO_URL", "").strip()
    username = os.getenv("TWITCH_USERNAME", "").strip()
    token = os.getenv("TWITCH_OAUTH_TOKEN", "").strip()
    if not source_url:
        raise SystemExit("Set LIVE_VIDEO_URL to an authorised direct media URL.")
    if not username or not token:
        raise SystemExit("Set TWITCH_USERNAME and TWITCH_OAUTH_TOKEN (chat:read scope).")
    if not args.confirm_rights:
        raise SystemExit("Pass --confirm-rights after confirming recording/reuse permission.")
    if args.transcribe and transcribe_file is None:
        raise SystemExit("Transcription helper is unavailable; run this script from the repository checkout.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = SpikeConfig(
        min_messages=args.min_messages,
        ratio_threshold=args.ratio_threshold,
        cooldown_seconds=args.cooldown_seconds,
        clip_seconds=args.clip_seconds,
        pre_roll_seconds=args.pre_roll_seconds,
        post_roll_seconds=args.post_roll_seconds,
    )
    if config.pre_roll_seconds + config.post_roll_seconds != config.clip_seconds:
        raise SystemExit("--pre-roll plus --post-roll must equal --clip-seconds.")

    recorder = SegmentRecorder(
        source_url=source_url,
        output_dir=output_dir,
        ffmpeg_bin=args.ffmpeg,
        segment_seconds=args.segment_seconds,
    )
    recorder.start()
    recording_started_at = datetime.now(timezone.utc)
    detector = ChatSpikeDetector(config)
    reader = TwitchIRCReader(username, token, args.channel)
    print(f"Recording authorised source; listening to #{args.channel}.")
    print(f"Output directory: {output_dir}")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    async def consume_chat() -> None:
        async for message in reader.messages():
            spike = detector.add_message(message.received_at)
            if spike is None:
                continue
            event_seconds = max(
                0.0, (message.received_at - recording_started_at).total_seconds()
                + args.sync_offset_seconds
            )
            stamp = spike.timestamp_utc.replace(":", "").replace("-", "")
            clip_path = output_dir / f"{args.channel}_{stamp}.mp4"
            print(
                f"Chat spike: {spike.messages_in_bucket} messages / "
                f"{config.bucket_seconds}s (baseline median {spike.baseline_median:.1f})."
            )
            try:
                clip = await asyncio.to_thread(
                    recorder.extract_spike_clip,
                    event_seconds,
                    clip_path,
                    config.pre_roll_seconds,
                    config.post_roll_seconds,
                    args.post_roll_timeout,
                )
                save_spike_metadata(spike, clip, output_dir)
                print(f"Saved candidate clip: {clip}")
                if args.transcribe and transcribe_file is not None:
                    transcript = await asyncio.to_thread(
                        transcribe_file, clip, args.whisper_model, args.whisper_device
                    )
                    print(f"Saved transcript: {transcript}")
            except Exception as exc:
                print(f"Clip processing failed: {type(exc).__name__}: {exc}")

    consumer = asyncio.create_task(consume_chat())
    try:
        await stop_event.wait()
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        recorder.stop()
        print("Live clipper stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect Twitch chat spikes and clip an authorised live video source.")
    parser.add_argument("--channel", required=True, help="Twitch channel whose chat you are authorised to monitor.")
    parser.add_argument("--output-dir", default="data/live_clips")
    parser.add_argument("--confirm-rights", action="store_true", help="Confirm you have permission to record and reuse the video.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--segment-seconds", type=int, default=5)
    parser.add_argument("--min-messages", type=int, default=8)
    parser.add_argument("--ratio-threshold", type=float, default=2.5)
    parser.add_argument("--cooldown-seconds", type=int, default=45)
    parser.add_argument("--clip-seconds", type=int, default=30)
    parser.add_argument("--pre-roll-seconds", type=int, default=15)
    parser.add_argument("--post-roll-seconds", type=int, default=15)
    parser.add_argument("--post-roll-timeout", type=int, default=90)
    parser.add_argument("--sync-offset-seconds", type=float, default=0.0)
    parser.add_argument("--transcribe", action="store_true", help="Run faster-whisper on each extracted clip.")
    parser.add_argument("--whisper-model", choices=["tiny", "base", "small", "medium"], default="tiny")
    parser.add_argument("--whisper-device", choices=["cpu", "cuda"], default="cpu")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
