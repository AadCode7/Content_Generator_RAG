"""Small typed data structures shared by collectors and the research pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class SourceArticle:
    source_id: int
    source_name: str
    url: str
    title: str
    summary: str = ""
    content: str = ""
    published_at: str = ""
    domain: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanSummary:
    sources_checked: int = 0
    articles_found: int = 0
    articles_new: int = 0
    articles_analyzed: int = 0
    discoveries_saved: int = 0
    duplicates_skipped: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
