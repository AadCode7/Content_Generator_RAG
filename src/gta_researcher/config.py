"""Application configuration and default source definitions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "openai/gpt-oss-20b"

DEFAULT_SOURCES = [
    {
        "name": "Rockstar Games Newswire",
        "url": "https://www.rockstargames.com/newswire",
        "kind": "webpage",
        "description": "Official Rockstar announcements and updates.",
    },
    {
        "name": "Grand Theft Auto VI official site",
        "url": "https://www.rockstargames.com/VI",
        "kind": "webpage",
        "description": "Official GTA VI information, media and announcements.",
    },
    {
        "name": "IGN",
        "url": "https://www.ign.com/rss/v2/articles/feed",
        "kind": "rss",
        "description": "Gaming news and reporting.",
    },
    {
        "name": "PC Gamer",
        "url": "https://www.pcgamer.com/feeds.xml",
        "kind": "rss",
        "description": "Gaming reporting, guides and features.",
    },
    {
        "name": "Kotaku",
        "url": "https://kotaku.com/feed",
        "kind": "rss",
        "description": "Gaming news and community coverage.",
    },
]

@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    database_path: Path
    request_timeout_seconds: int
    max_articles_per_source: int
    max_article_chars: int
    min_article_chars: int

def get_settings() -> Settings:
    """Read environment settings. Secrets are never stored in this module."""
    database_value = os.getenv("DATABASE_PATH", "data/gta_researcher.db")
    database_path = Path(database_value)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        database_path=database_path,
        request_timeout_seconds=max(5, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))),
        max_articles_per_source=max(1, min(30, int(os.getenv("MAX_ARTICLES_PER_SOURCE", "8")))),
        max_article_chars=max(2000, min(30000, int(os.getenv("MAX_ARTICLE_CHARS", "12000")))),
        min_article_chars=max(80, int(os.getenv("MIN_ARTICLE_CHARS", "180"))),
    )
