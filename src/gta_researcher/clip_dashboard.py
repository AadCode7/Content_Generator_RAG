"""Filesystem-backed clip review helpers for the Streamlit dashboard."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REVIEW_STATES = {"pending", "approved", "rejected"}


def number_value(value: Any, default: float = 0.0) -> float:
    """Convert metadata values safely; malformed sidecar fields must not break the UI."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number == number and abs(number) != float("inf") else default


@dataclass(frozen=True)
class ClipCandidate:
    clip_path: Path
    metadata_path: Path
    metadata: dict[str, Any]
    transcript_path: Path | None
    transcript: dict[str, Any] | None

    @property
    def review_status(self) -> str:
        value = str(self.metadata.get("review_status", "pending")).lower()
        return value if value in REVIEW_STATES else "pending"


def _safe_child_path(root: Path, candidate: str | Path) -> Path | None:
    """Resolve a candidate path and reject anything outside the configured clip folder."""
    try:
        resolved_root = root.resolve()
        resolved = Path(candidate).expanduser()
        if not resolved.is_absolute():
            resolved = resolved_root / resolved
        resolved = resolved.resolve()
        if not resolved.is_relative_to(resolved_root):
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def list_clip_candidates(output_dir: str | Path) -> list[ClipCandidate]:
    """Load clips with metadata sidecars; ignore malformed or unsafe entries."""
    root = Path(output_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return []

    candidates: list[ClipCandidate] = []
    for discovered_metadata_path in root.glob("*.json"):
        if discovered_metadata_path.name.endswith(".transcript.json"):
            continue
        metadata_path = _safe_child_path(root, discovered_metadata_path)
        if metadata_path is None or not metadata_path.is_file():
            continue
        metadata = _load_json(metadata_path)
        if metadata is None:
            continue

        raw_clip_path = metadata.get("clip_path") or metadata_path.with_suffix(".mp4")
        clip_path = _safe_child_path(root, raw_clip_path)
        if clip_path is None or not clip_path.is_file() or clip_path.suffix.lower() != ".mp4":
            continue

        transcript_path = _safe_child_path(root, clip_path.with_suffix(".transcript.json"))
        transcript = (
            _load_json(transcript_path)
            if transcript_path is not None and transcript_path.is_file()
            else None
        )
        candidates.append(
            ClipCandidate(
                clip_path=clip_path,
                metadata_path=metadata_path,
                metadata=metadata,
                transcript_path=transcript_path if transcript is not None and transcript_path is not None else None,
                transcript=transcript,
            )
        )

    candidates.sort(
        key=lambda item: number_value(item.metadata.get("timestamp", 0)),
        reverse=True,
    )
    return candidates


def update_clip_review_status(candidate: ClipCandidate, status: str) -> None:
    """Persist a manual review decision in the clip's JSON sidecar."""
    normalized = status.strip().lower()
    if normalized not in REVIEW_STATES:
        raise ValueError(f"Review status must be one of: {', '.join(sorted(REVIEW_STATES))}.")
    payload = dict(candidate.metadata)
    payload["review_status"] = normalized
    payload["clip_path"] = str(candidate.clip_path)
    temporary_path = candidate.metadata_path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary_path.replace(candidate.metadata_path)


def transcript_text(transcript: dict[str, Any] | None) -> str:
    """Flatten faster-whisper segment output for readable review and search."""
    if not transcript:
        return ""
    segments = transcript.get("segments", [])
    if not isinstance(segments, list):
        return ""
    lines: list[str] = []
    for segment in segments:
        if isinstance(segment, dict):
            text = str(segment.get("text", "")).strip()
            if text:
                lines.append(text)
    return " ".join(lines)
