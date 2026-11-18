"""Orchestrate collection, Groq analysis and opportunity ranking."""

from __future__ import annotations

import re
from typing import Any

from gta_researcher.collectors import collect_source_articles
from gta_researcher.models import ScanSummary
from gta_researcher.scoring import fingerprint, score_discovery
from gta_researcher.storage import ResearchStore
from gta_researcher.speech import compose_voiceover_text


def _as_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value).strip()


def _normalize_discovery(
    raw: dict[str, Any], article: dict[str, Any], article_id: int
) -> dict[str, Any] | None:
    title = _as_text(raw.get("title"))
    claim = _as_text(raw.get("claim"))
    if not title or not (claim or _as_text(raw.get("explanation"))):
        return None

    item: dict[str, Any] = {
        "fingerprint": fingerprint(f"{article_id}:{title}:{raw.get('claim', '')}"),
        "title": title[:300],
        "category": _as_text(raw.get("category"), "Gameplay detail")[:80],
        "claim": claim[:2000],
        "explanation": _as_text(raw.get("explanation"))[:4000],
        "player_takeaway": _as_text(raw.get("player_takeaway"))[:2500],
        "caption": _as_text(raw.get("caption"))[:500],
        "description": _as_text(raw.get("description"))[:3000],
        "mentions": [
            _as_text(handle)[:32]
            for handle in raw.get("mentions", [])
            if re.fullmatch(r"@[A-Za-z0-9._]{1,30}", _as_text(handle))
        ][:8] if isinstance(raw.get("mentions", []), list) else [],
        "evidence_quote": _as_text(raw.get("evidence_quote"))[:1500],
        "evidence_type": _as_text(raw.get("evidence_type"), "needs_verification")[:60],
        "evidence_supported": False,
        "why_interesting": _as_text(raw.get("why_interesting"))[:2000],
        "clip_angle": _as_text(raw.get("clip_angle"))[:1000],
        "series": _as_text(raw.get("series"), "Things You Missed in GTA VI")[:100],
        "hook": _as_text(raw.get("hook"))[:500],
        "script": compose_voiceover_text(
            _as_text(raw.get("hook"))[:500],
            _as_text(raw.get("script"))[:6000],
        )[:6000],
        "visual_notes": _as_text(raw.get("visual_notes"))[:2000],
        "hashtags": [
            _as_text(tag)[:60]
            for tag in raw.get("hashtags", [])
            if _as_text(tag)
        ][:12] if isinstance(raw.get("hashtags", []), list) else [],
    }
    item.update(score_discovery(raw))
    return item


def scan_sources(store: ResearchStore, settings: Any) -> ScanSummary:
    """Collect article URLs from all active configured sources."""
    summary = ScanSummary()
    for source in store.list_sources(active_only=True):
        summary.sources_checked += 1
        try:
            collected = collect_source_articles(
                source=source,
                timeout=settings.request_timeout_seconds,
                max_articles=settings.max_articles_per_source,
                max_article_chars=settings.max_article_chars,
            )
            summary.articles_found += len(collected)
            for article in collected:
                _, inserted = store.save_article(article.to_dict())
                if inserted:
                    summary.articles_new += 1
            store.update_source_result(int(source["id"]))
        except Exception as exc:
            message = f"{source['name']}: {type(exc).__name__}: {exc}"
            summary.errors.append(message)
            store.update_source_result(int(source["id"]), message)
    return summary


def analyze_pending_articles(
    store: ResearchStore, researcher: Any, limit: int = 30
) -> ScanSummary:
    """Analyze collected articles without claim verification or story-similarity filtering."""
    summary = ScanSummary()
    articles = store.list_pending_articles(limit=max(1, min(200, limit)))
    for article in articles:
        try:
            raw_discoveries = researcher.analyze_article(article)
            for raw in raw_discoveries:
                item = _normalize_discovery(raw, article, int(article["id"]))
                if item:
                    store.add_discovery(int(article["id"]), item)
                    summary.discoveries_saved += 1
            store.set_article_ai_status(int(article["id"]), "processed")
            summary.articles_analyzed += 1
        except Exception as exc:
            message = f"{article.get('title', 'Article')}: {type(exc).__name__}: {exc}"
            summary.errors.append(message)
            store.set_article_ai_status(int(article["id"]), "failed", message)
    return summary


def run_research_cycle(store: ResearchStore, settings: Any, researcher: Any) -> ScanSummary:
    """Collect source content, then analyze pending articles in one user-triggered cycle."""
    summary = scan_sources(store, settings)
    analysis = analyze_pending_articles(store, researcher)
    summary.articles_analyzed = analysis.articles_analyzed
    summary.discoveries_saved = analysis.discoveries_saved
    summary.errors.extend(analysis.errors or [])
    return summary
