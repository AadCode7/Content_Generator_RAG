"""Content opportunity scoring helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def clamp_score(value: Any, default: int = 5) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        number = default
    return max(1, min(10, number))


def score_discovery(item: dict[str, Any]) -> dict[str, int | float]:
    """Rank ideas by novelty, shareability and visual potential."""
    novelty = clamp_score(item.get("novelty_score"))
    shareability = clamp_score(item.get("shareability_score"))
    visual = clamp_score(item.get("visual_potential_score"))
    try:
        confidence = max(0, min(100, int(float(item.get("confidence", 50) or 50))))
    except (TypeError, ValueError, OverflowError):
        confidence = 50
    raw = novelty * 0.35 + shareability * 0.35 + visual * 0.30
    confidence_factor = 0.55 + confidence / 100.0 * 0.45
    return {
        "novelty_score": novelty,
        "shareability_score": shareability,
        "visual_potential_score": visual,
        "confidence": confidence,
        "overall_score": round(raw * confidence_factor, 1),
    }


def normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def fingerprint(value: str) -> str:
    """Create a metadata fingerprint; this is not used to suppress stories."""
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()
