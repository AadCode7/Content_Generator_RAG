"""RSS and webpage collection with basic URL safety and text extraction."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup

from gta_researcher.models import SourceArticle

USER_AGENT = "GTA-VI-News-Researcher/0.1"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/rss+xml,application/xml,application/atom+xml",
}
RELEVANCE_TERMS = (
    "gta vi", "gta 6", "grand theft auto vi", "grand theft auto 6",
    "vice city", "leonida", "jason duval", "lucia camino",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid http or https URL.")
    query_parts = [
        part for part in parsed.query.split("&")
        if part and not part.lower().startswith(("utm_", "fbclid=", "gclid="))
    ]
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
        query="&".join(query_parts),
    )
    return urlunparse(normalized).rstrip("/")


def validate_public_url(url: str) -> str:
    """Reject localhost, private IPs and hostnames resolving to non-public addresses."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Localhost URLs are not allowed.")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve source hostname: {host}") from exc
        if not resolved:
            raise ValueError(f"Could not resolve source hostname: {host}")
        for item in resolved:
            if not ipaddress.ip_address(item[4][0]).is_global:
                raise ValueError("The source hostname resolves to a private or non-public address.")
    else:
        if not address.is_global:
            raise ValueError("Private or non-public IP addresses are not allowed.")
    return normalized


def is_gta_relevant(title: str, summary: str = "", url: str = "") -> bool:
    text = re.sub(r"[^a-z0-9]+", " ", f"{title} {summary} {url}".lower())
    return any(term in text for term in RELEVANCE_TERMS)


def _clean(value: str, max_chars: int = 12000) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:max_chars]


def _safe_get(url: str, timeout: int) -> requests.Response:
    """Fetch a public URL while validating each redirect destination."""
    current_url = validate_public_url(url)
    for _ in range(6):
        response = requests.get(
            current_url,
            headers=REQUEST_HEADERS,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code in REDIRECT_CODES:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise ValueError("Source returned a redirect without a Location header.")
            current_url = validate_public_url(urljoin(current_url, location))
            continue
        response.raise_for_status()
        validate_public_url(response.url)
        return response
    raise ValueError("Source returned too many redirects.")


def _fetch_html(url: str, timeout: int) -> str:
    response = _safe_get(url, timeout)
    content_type = response.headers.get("content-type", "").lower()
    if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml")):
        raise ValueError(f"Expected an HTML page, received {content_type}.")
    if len(response.content) > 4_000_000:
        raise ValueError("Source page is larger than the 4 MB safety limit.")
    return response.text


def _extract_page_text(html: str, url: str, max_chars: int) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not extracted:
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            tag.decompose()
        extracted = soup.get_text(" ", strip=True)
    return title, _clean(extracted or "", max_chars)


def _fetch_article_text(url: str, timeout: int, max_chars: int) -> str:
    try:
        html = _fetch_html(url, timeout)
        _, text = _extract_page_text(html, url, max_chars)
        return text
    except (requests.RequestException, ValueError, OSError):
        return ""


def collect_rss(
    source: dict,
    timeout: int,
    max_articles: int,
    max_article_chars: int,
) -> list[SourceArticle]:
    feed_url = validate_public_url(source["url"])
    response = _safe_get(feed_url, timeout)
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Feed could not be parsed: {parsed.bozo_exception}")

    output: list[SourceArticle] = []
    for entry in parsed.entries:
        title = _clean(entry.get("title", ""), 300)
        link = entry.get("link", "")
        summary_html = entry.get("summary", "") or entry.get("description", "")
        summary = _clean(
            BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True), 2500
        )
        if not title or not link or not is_gta_relevant(title, summary, link):
            continue

        try:
            link = validate_public_url(urljoin(feed_url, link))
        except ValueError:
            continue

        content = _fetch_article_text(link, timeout, max_article_chars)
        if len(content) < 100:
            content = summary
        published = entry.get("published", "") or entry.get("updated", "")
        output.append(SourceArticle(
            source_id=int(source["id"]),
            source_name=source["name"],
            url=link,
            title=title,
            summary=summary,
            content=content,
            published_at=published,
            domain=urlparse(link).hostname or "",
        ))
        if len(output) >= max_articles:
            break
    return output


def collect_webpage(
    source: dict,
    timeout: int,
    max_articles: int,
    max_article_chars: int,
) -> list[SourceArticle]:
    page_url = validate_public_url(source["url"])
    html = _fetch_html(page_url, timeout)
    page_title, page_text = _extract_page_text(html, page_url, max_article_chars)
    soup = BeautifulSoup(html, "html.parser")
    page_host = (urlparse(page_url).hostname or "").lower()
    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        title = _clean(anchor.get_text(" ", strip=True), 300)
        if not href:
            continue
        try:
            absolute = validate_public_url(urljoin(page_url, href))
        except ValueError:
            continue
        parsed_link = urlparse(absolute)
        link_host = (parsed_link.hostname or "").lower()
        if link_host != page_host or absolute == page_url or absolute in seen:
            continue
        if not is_gta_relevant(title, absolute):
            continue
        seen.add(absolute)
        links.append((title or absolute.rsplit("/", 1)[-1], absolute))

    output: list[SourceArticle] = []
    for title, link in links[:max_articles]:
        content = _fetch_article_text(link, timeout, max_article_chars)
        if len(content) < 100:
            continue
        output.append(SourceArticle(
            source_id=int(source["id"]),
            source_name=source["name"],
            url=link,
            title=title,
            summary=content[:1200],
            content=content,
            domain=urlparse(link).hostname or "",
        ))

    if not output and len(page_text) >= 180 and is_gta_relevant(page_title, page_text, page_url):
        output.append(SourceArticle(
            source_id=int(source["id"]),
            source_name=source["name"],
            url=page_url,
            title=page_title or source["name"],
            summary=page_text[:1200],
            content=page_text,
            domain=urlparse(page_url).hostname or "",
        ))
    return output[:max_articles]


def collect_source_articles(
    source: dict,
    timeout: int,
    max_articles: int,
    max_article_chars: int,
) -> list[SourceArticle]:
    if source["kind"] == "rss":
        return collect_rss(source, timeout, max_articles, max_article_chars)
    if source["kind"] == "webpage":
        return collect_webpage(source, timeout, max_articles, max_article_chars)
    raise ValueError(f"Unsupported source type: {source['kind']}")
