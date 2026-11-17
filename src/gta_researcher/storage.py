"""SQLite persistence for sources, collected articles and content discoveries."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gta_researcher.config import DEFAULT_SOURCES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ResearchStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        self.seed_default_sources()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL CHECK(kind IN ('rss', 'webpage')),
                    description TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    last_checked TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL REFERENCES sources(id),
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL,
                    ai_status TEXT NOT NULL DEFAULT 'pending',
                    ai_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS discoveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL REFERENCES articles(id),
                    fingerprint TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Gameplay detail',
                    claim TEXT NOT NULL DEFAULT '',
                    explanation TEXT NOT NULL DEFAULT '',
                    evidence_quote TEXT NOT NULL DEFAULT '',
                    evidence_type TEXT NOT NULL DEFAULT 'needs_verification',
                    evidence_supported INTEGER NOT NULL DEFAULT 0,
                    why_interesting TEXT NOT NULL DEFAULT '',
                    clip_angle TEXT NOT NULL DEFAULT '',
                    series TEXT NOT NULL DEFAULT 'Things You Missed in GTA VI',
                    hook TEXT NOT NULL DEFAULT '',
                    script TEXT NOT NULL DEFAULT '',
                    visual_notes TEXT NOT NULL DEFAULT '',
                    hashtags_json TEXT NOT NULL DEFAULT '[]',
                    novelty_score INTEGER NOT NULL DEFAULT 5,
                    shareability_score INTEGER NOT NULL DEFAULT 5,
                    visual_potential_score INTEGER NOT NULL DEFAULT 5,
                    confidence INTEGER NOT NULL DEFAULT 50,
                    overall_score REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'new'
                        CHECK(status IN ('new', 'approved', 'rejected', 'used')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_articles_ai_status ON articles(ai_status);
                CREATE INDEX IF NOT EXISTS idx_discoveries_status_score
                    ON discoveries(status, overall_score DESC);
                """
            )

    def seed_default_sources(self) -> None:
        for source in DEFAULT_SOURCES:
            self.add_source(
                name=source["name"], url=source["url"], kind=source["kind"],
                description=source["description"], ignore_existing=True,
            )

    def add_source(
        self, name: str, url: str, kind: str, description: str = "",
        ignore_existing: bool = False,
    ) -> int | None:
        if kind not in {"rss", "webpage"}:
            raise ValueError("Source type must be rss or webpage.")
        if not name.strip() or not url.strip():
            raise ValueError("Source name and URL are required.")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO sources
                    (name, url, kind, description, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (name.strip(), url.strip(), kind, description.strip(), utc_now()),
            )
            if cursor.rowcount:
                return int(cursor.lastrowid)
            if ignore_existing:
                row = connection.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
                return int(row["id"]) if row else None
            raise ValueError("This source URL has already been added.")

    def list_sources(self, active_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM sources"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name COLLATE NOCASE"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def set_source_active(self, source_id: int, active: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE sources SET active = ? WHERE id = ?",
                (1 if active else 0, source_id),
            )

    def update_source_result(self, source_id: int, error: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE sources SET last_checked = ?, last_error = ? WHERE id = ?",
                (utc_now(), error[:1000], source_id),
            )

    def save_article(self, article: dict[str, Any]) -> tuple[int, bool]:
        """Insert an article URL once, or refresh it without resetting analysis status."""
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id, content FROM articles WHERE url = ?", (article["url"],)
            ).fetchone()
            if existing:
                if len(article.get("content", "")) > len(existing["content"] or ""):
                    connection.execute(
                        """
                        UPDATE articles SET title = ?, summary = ?, content = ?,
                            published_at = ?, fetched_at = ?, domain = ?
                        WHERE id = ?
                        """,
                        (
                            article["title"], article.get("summary", ""),
                            article.get("content", ""), article.get("published_at", ""),
                            utc_now(), article.get("domain", ""), existing["id"],
                        ),
                    )
                return int(existing["id"]), False
            cursor = connection.execute(
                """
                INSERT INTO articles
                    (source_id, url, title, domain, summary, content, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article["source_id"], article["url"], article["title"],
                    article.get("domain", ""), article.get("summary", ""),
                    article.get("content", ""), article.get("published_at", ""), utc_now(),
                ),
            )
            return int(cursor.lastrowid), True

    def list_pending_articles(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return articles that are pending or failed and can be analysed/retried."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.*, s.name AS source_name FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.ai_status IN ('pending', 'failed')
                ORDER BY a.fetched_at DESC LIMIT ?
                """,
                (max(1, min(500, int(limit))),),
            ).fetchall()
            return [dict(row) for row in rows]

    def article_status_counts(self) -> dict[str, int]:
        """Return article totals grouped by AI processing state."""
        counts = {"pending": 0, "failed": 0, "processed": 0}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT ai_status, COUNT(*) AS total FROM articles GROUP BY ai_status"
            ).fetchall()
        for row in rows:
            status = str(row["ai_status"])
            if status in counts:
                counts[status] = int(row["total"])
        return counts

    def list_failed_articles(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return failed article analyses with source names and stored error details."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.*, s.name AS source_name FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.ai_status = 'failed'
                ORDER BY a.fetched_at DESC LIMIT ?
                """,
                (max(1, min(500, int(limit))),),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_article_ai_status(self, article_id: int, status: str, error: str = "") -> None;
        if status not in {"pending", "processed", "failed"}:
            raise ValueError("Invalid article analysis state.")
        with self.connect() as connection:
            connection.execute(
                "UPDATE articles SET ai_status = ?, ai_error = ? WHERE id = ?",
                (status, error[:1000], article_id),
            )

    def add_discovery(self, article_id: int, item: dict[str, Any]) -> bool:
        """Store each generated idea without cross-source similarity filtering."""
        now = utc_now()
        values = (
            article_id, item["fingerprint"], item["title"], item.get("category", "Gameplay detail"),
            item.get("claim", ""), item.get("explanation", ""), item.get("evidence_quote", ""),
            item.get("evidence_type", "needs_verification"),
            1 if item.get("evidence_supported") else 0, item.get("why_interesting", ""),
            item.get("clip_angle", ""), item.get("series", "Things You Missed in GTA VI"),
            item.get("hook", ""), item.get("script", ""), item.get("visual_notes", ""),
            json.dumps(item.get("hashtags", []), ensure_ascii=False),
            item.get("novelty_score", 5), item.get("shareability_score", 5),
            item.get("visual_potential_score", 5), item.get("confidence", 50),
            item.get("overall_score", 0), now, now,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO discoveries (
                    article_id, fingerprint, title, category, claim, explanation,
                    evidence_quote, evidence_type, evidence_supported, why_interesting,
                    clip_angle, series, hook, script, visual_notes, hashtags_json,
                    novelty_score, shareability_score, visual_potential_score,
                    confidence, overall_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return True

    def list_discoveries(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        query = """
            SELECT d.*, a.url AS source_url, a.title AS article_title,
                   a.domain AS source_domain, a.published_at, s.name AS source_name
            FROM discoveries d
            JOIN articles a ON a.id = d.article_id
            JOIN sources s ON s.id = a.source_id
        """
        params: list[Any] = []
        if status and status != "all":
            query += " WHERE d.status = ?"
            params.append(status)
        query += " ORDER BY d.overall_score DESC, d.created_at DESC LIMIT ?"
        params.append(max(1, min(500, int(limit))))
        with self.connect() as connection:
            result = []
            for row in connection.execute(query, params).fetchall():
                item = dict(row)
                try:
                    item["hashtags"] = json.loads(item.pop("hashtags_json", "[]"))
                except (TypeError, json.JSONDecodeError):
                    item["hashtags"] = []
                result.append(item)
            return result

    def get_discovery(self, discovery_id: int) -> dict[str, Any] | None:
        return next(
            (item for item in self.list_discoveries(limit=500) if item["id"] == discovery_id),
            None,
        )

    def update_discovery_status(self, discovery_id: int, status: str) -> None:
        if status not in {"new", "approved", "rejected", "used"}:
            raise ValueError("Invalid discovery status.")
        with self.connect() as connection:
            connection.execute(
                "UPDATE discoveries SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), discovery_id),
            )

    def update_discovery_script(
        self, discovery_id: int, hook: str, script: str, visual_notes: str = ""
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE discoveries SET hook = ?, script = ?, visual_notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (hook, script, visual_notes, utc_now(), discovery_id),
            )

    def dashboard_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            return {
                "sources": int(connection.execute(
                    "SELECT COUNT(*) FROM sources WHERE active = 1"
                ).fetchone()[0]),
                "articles": int(connection.execute(
                    "SELECT COUNT(*) FROM articles"
                ).fetchone()[0]),
                "new": int(connection.execute(
                    "SELECT COUNT(*) FROM discoveries WHERE status = 'new'"
                ).fetchone()[0]),
                "approved": int(connection.execute(
                    "SELECT COUNT(*) FROM discoveries WHERE status = 'approved'"
                ).fetchone()[0]),
            }
