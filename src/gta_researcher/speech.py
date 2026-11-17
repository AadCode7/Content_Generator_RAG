"""Female neural voiceover generation and WAV helpers."""

from __future__ import annotations

import asyncio
import io
import re
import wave
from typing import Any

DEFAULT_VOICE = "en-GB-SoniaNeural"
DEFAULT_RATE = "+10%"
DEFAULT_PITCH = "+1Hz"
VOICE_PROFILE_NAME = "Fast-paced British gaming presenter"
VOICE_PROFILE_DESCRIPTION = (
    "British English female voice with a brisk, lively presenter cadence, clear articulation, "
    "confident delivery and a lightly lifted pitch."
)
SAMPLE_RATE = 24_000
MIN_VOICEOVER_WORDS = 150
VOICEOVER_WORDS_PER_MINUTE = 150


def count_words(text: str) -> int:
    """Count spoken words without counting punctuation-only tokens."""
    return len(re.findall(r"[\w]+(?:['’][\w]+)?", text or "", flags=re.UNICODE))


def compose_voiceover_text(hook: str, script: str) -> str:
    """Ensure the opening hook is spoken once at the start of the narration."""
    hook = (hook or "").strip()
    script = (script or "").strip()
    if not hook:
        return script
    if not script:
        return hook
    if script.casefold().startswith(hook.casefold()):
        return script
    return f"{hook}\n\n{script}"


def estimate_duration_seconds(text: str) -> int:
    """Estimate narration duration at the configured 150 words per minute."""
    return round(count_words(text) * 60 / VOICEOVER_WORDS_PER_MINUTE)


def pcm_to_wav(
    pcm_data: bytes,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap signed 16-bit PCM samples in a standards-compliant WAV container."""
    if not pcm_data:
        raise ValueError("The speech provider returned empty audio.")
    if sample_rate <= 0 or channels <= 0 or sample_width not in {1, 2, 3, 4}:
        raise ValueError("Invalid WAV audio format settings.")
    frame_width = channels * sample_width
    if len(pcm_data) % frame_width:
        raise ValueError("PCM audio data is not aligned to a complete audio frame.")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return output.getvalue()


async def _synthesize_mp3(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=DEFAULT_RATE,
        pitch=DEFAULT_PITCH,
    )
    audio_parts: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio_part = chunk.get("data", b"")
            if audio_part:
                audio_parts.append(audio_part)
    audio = b"".join(audio_parts)
    if not audio:
        raise RuntimeError("The neural voice service returned no audio.")
    return audio


def generate_voiceover_wav(
    text: str,
    voice: str = DEFAULT_VOICE,
) -> bytes:
    """Generate an energetic British female presenter voiceover as WAV audio."""
    narration = (text or "").strip()
    if not narration:
        raise ValueError("Add a voiceover script before generating audio.")
    if len(narration) > 12_000:
        raise ValueError("The voiceover is too long to synthesize in one request.")
    if not voice.strip():
        raise ValueError("A supported neural voice must be selected.")

    try:
        mp3_audio = asyncio.run(_synthesize_mp3(narration, voice.strip()))
    except RuntimeError as exc:
        if "asyncio.run()" in str(exc):
            raise RuntimeError(
                "Speech generation could not start because an asyncio event loop is already running."
            ) from exc
        raise

    try:
        import miniaudio
    except ImportError as exc:
        raise RuntimeError(
            "WAV audio conversion is unavailable. Install the miniaudio package and restart the app."
        ) from exc

    decoded: Any = miniaudio.decode(
        mp3_audio,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=SAMPLE_RATE,
    )
    return pcm_to_wav(
        decoded.samples.tobytes(),
        sample_rate=decoded.sample_rate,
        channels=decoded.nchannels,
        sample_width=2,
    )
