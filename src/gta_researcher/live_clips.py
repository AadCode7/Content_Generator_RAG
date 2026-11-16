"""Chat-spike detection and FFmpeg segment-buffer clip extraction.

The recorder consumes an explicitly supplied, authorised media URL. It does not
resolve creator pages, bypass access controls, or download platform VODs.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class SpikeConfig:
    bucket_seconds: int = 10
    baseline_buckets: int = 60
    min_messages: int = 8
    ratio_threshold: float = 2.5
    mad_multiplier: float = 3.0
    cooldown_seconds: int = 45
    clip_seconds: int = 30
    pre_roll_seconds: int = 15
    post_roll_seconds: int = 15

    def __post_init__(self) -> None:
        if self.bucket_seconds <= 0 or self.baseline_buckets < 2:
            raise ValueError("Bucket duration must be positive and baseline needs at least 2 buckets.")
        if self.min_messages < 1 or self.ratio_threshold <= 1 or self.mad_multiplier < 0:
            raise ValueError("Spike thresholds must be positive; ratio_threshold must exceed 1.")
        if self.cooldown_seconds < 0 or self.clip_seconds <= 0:
            raise ValueError("Cooldown cannot be negative and clip duration must be positive.")
        if self.pre_roll_seconds < 0 or self.post_roll_seconds < 0:
            raise ValueError("Pre-roll and post-roll cannot be negative.")
        if self.pre_roll_seconds + self.post_roll_seconds != self.clip_seconds:
            raise ValueError("Pre-roll plus post-roll must equal clip_seconds.")


@dataclass(frozen=True)
class ChatSpike:
    timestamp: float
    bucket_start: float
    messages_in_bucket: int
    baseline_median: float
    baseline_mad: float
    activity_ratio: float
    threshold: float

    @property
    def timestamp_utc(self) -> str:
        return datetime.fromtimestamp(self.timestamp, timezone.utc).isoformat()


class ChatSpikeDetector:
    """Detects unusual message bursts relative to a channel's recent baseline."""

    def __init__(self, config: SpikeConfig | None = None) -> None:
        self.config = config or SpikeConfig()
        self._counts: dict[int, int] = defaultdict(int)
        self._last_spike = float("-inf")

    def add_message(self, timestamp: float | datetime | None = None) -> ChatSpike | None:
        if timestamp is None:
            epoch = time.time()
        elif isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                raise ValueError("Chat message timestamps must be timezone-aware.")
            epoch = timestamp.timestamp()
        else:
            epoch = float(timestamp)
        if not math.isfinite(epoch):
            raise ValueError("Timestamp must be a finite epoch value.")

        bucket = int(epoch // self.config.bucket_seconds)
        self._counts[bucket] += 1
        first_baseline_bucket = bucket - self.config.baseline_buckets
        baseline = [
            self._counts.get(index, 0)
            for index in range(first_baseline_bucket, bucket)
        ]
        for old_bucket in list(self._counts):
            if old_bucket < first_baseline_bucket:
                del self._counts[old_bucket]

        current_count = self._counts[bucket]
        baseline_median = float(median(baseline)) if baseline else 0.0
        deviations = [abs(value - baseline_median) for value in baseline]
        baseline_mad = float(median(deviations)) if deviations else 0.0
        threshold = max(
            float(self.config.min_messages),
            baseline_median * self.config.ratio_threshold,
            baseline_median + self.config.mad_multiplier * max(baseline_mad, 1.0),
        )
        ratio = current_count / max(baseline_median, 1.0)

        if current_count < threshold:
            return None
        if epoch - self._last_spike < self.config.cooldown_seconds:
            return None

        self._last_spike = epoch
        return ChatSpike(
            timestamp=epoch,
            bucket_start=bucket * self.config.bucket_seconds,
            messages_in_bucket=current_count,
            baseline_median=baseline_median,
            baseline_mad=baseline_mad,
            activity_ratio=ratio,
            threshold=threshold,
        )


@dataclass(frozen=True)
class Segment:
    path: Path
    start: float
    end: float


class SegmentRecorder:
    """Records an authorised media URL into short MPEG-TS segments.

    FFmpeg's CSV segment index provides media-timeline offsets. This makes it
    possible to select pre-roll and post-roll without reading a growing MP4.
    """

    def __init__(
        self,
        source_url: str,
        output_dir: str | Path,
        ffmpeg_bin: str = "ffmpeg",
        segment_seconds: int = 5,
    ) -> None:
        if not source_url.strip():
            raise ValueError("An authorised media URL is required.")
        if segment_seconds < 1:
            raise ValueError("segment_seconds must be at least 1.")
        self.source_url = source_url
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.segment_dir = self.output_dir / "segments"
        self.index_path = self.output_dir / "segments.csv"
        self.ffmpeg_bin = ffmpeg_bin
        self.segment_seconds = segment_seconds
        self.process: subprocess.Popen | None = None
        self._log_handle = None

    def start(self) -> None:
        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError(f"FFmpeg executable not found: {self.ffmpeg_bin}")
        self.segment_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.output_dir / "ffmpeg_recording.log"
        self._log_handle = log_path.open("a", encoding="utf-8")
        output_pattern = str(self.segment_dir / "segment_%06d.ts")
        command = [
            self.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-i", self.source_url, "-map", "0:v:0", "-map", "0:a?",
            "-c", "copy", "-f", "segment", "-segment_time", str(self.segment_seconds),
            "-segment_list", str(self.index_path), "-segment_list_type", "csv",
            "-segment_format", "mpegts", output_pattern,
        ]
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=self._log_handle,
            )
        except OSError:
            self._log_handle.close()
            self._log_handle = None
            raise

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def read_segments(self) -> list[Segment]:
        if not self.index_path.exists():
            return []
        segments: list[Segment] = []
        with self.index_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) < 3:
                    continue
                try:
                    path = Path(row[0])
                    if not path.is_absolute():
                        path = self.output_dir / path
                    start, end = float(row[1]), float(row[2])
                except (ValueError, OSError):
                    continue
                if end > start and path.is_file():
                    segments.append(Segment(path=path, start=start, end=end))
        return sorted(segments, key=lambda item: item.start)

    def extract_spike_clip(
        self,
        event_seconds: float,
        output_path: str | Path,
        pre_roll_seconds: int = 15,
        post_roll_seconds: int = 15,
        wait_timeout_seconds: int = 90,
    ) -> Path:
        if event_seconds < 0 or pre_roll_seconds < 0 or post_roll_seconds < 0:
            raise ValueError("Event and clip-window offsets cannot be negative.")
        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError(f"FFmpeg executable not found: {self.ffmpeg_bin}")
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        clip_start = max(0.0, event_seconds - pre_roll_seconds)
        clip_end = event_seconds + post_roll_seconds
        deadline = time.monotonic() + wait_timeout_seconds
        selected: list[Segment] = []
        while time.monotonic() < deadline:
            segments = self.read_segments()
            if segments and segments[-1].end >= clip_end:
                selected = [s for s in segments if s.end > clip_start and s.start < clip_end]
                break
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError("FFmpeg recording stopped before the clip's post-roll was captured.")
            time.sleep(0.5)
        if not selected:
            raise TimeoutError("Timed out waiting for the post-roll segments to finish.")
        if selected[0].start > clip_start + self.segment_seconds:
            raise RuntimeError("Pre-roll is incomplete; refusing to create a misleading clip.")

        concat_file = target.with_suffix(".concat.txt")
        try:
            with concat_file.open("w", encoding="utf-8") as handle:
                for segment in selected:
                    escaped = segment.path.as_posix().replace("'", "'\\''")
                    handle.write(f"file '{escaped}'\n")
            seek_from_concat_start = max(0.0, clip_start - selected[0].start)
            duration = clip_end - clip_start
            command = [
                self.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-ss", f"{seek_from_concat_start:.3f}", "-t", f"{duration:.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "22", "-c:a", "aac",
                "-b:a", "128k", "-movflags", "+faststart", str(target),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "FFmpeg failed to extract the clip.")[-2000:]
            raise RuntimeError(detail) from exc
        finally:
            concat_file.unlink(missing_ok=True)
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("FFmpeg completed without producing a valid clip.")
        return target


def save_spike_metadata(spike: ChatSpike, clip_path: Path, output_dir: Path) -> Path:
    """Persist a small JSON sidecar so clips remain traceable to chat activity."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = clip_path.with_suffix(".json")
    payload = asdict(spike)
    payload["timestamp_utc"] = spike.timestamp_utc
    payload["clip_path"] = str(clip_path)
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return metadata_path
