"""Optional faster-whisper transcription for generated candidate clips."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def transcribe_file(video_path: Path, model_name: str = "tiny", device: str = "cpu") -> Path:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Install transcription extras with: pip install -e '.[transcription]'"
        ) from exc

    compute_type = "int8" if device == "cpu" else "float16"
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(str(video_path), word_timestamps=True, vad_filter=True)
    rows = []
    for segment in segments:
        words = []
        for word in segment.words or []:
            words.append({"start": word.start, "end": word.end, "word": word.word})
        rows.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "words": words,
        })
    output_path = video_path.with_suffix(".transcript.json")
    output_path.write_text(
        json.dumps(
            {"language": info.language, "language_probability": info.language_probability, "segments": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe candidate clips with faster-whisper.")
    parser.add_argument("clip_dir", nargs="?", default="data/live_clips")
    parser.add_argument("--model", choices=["tiny", "base", "small", "medium"], default="tiny")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    directory = Path(args.clip_dir)
    clips = sorted(path for path in directory.glob("*.mp4") if not path.name.endswith(".transcript.mp4"))
    if not clips:
        print(f"No MP4 clips found in {directory}")
        return
    for clip in clips:
        try:
            transcript = transcribe_file(clip, args.model, args.device)
            print(f"{clip.name} -> {transcript.name}")
        except Exception as exc:
            print(f"{clip.name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
