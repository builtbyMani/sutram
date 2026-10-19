"""OSINT web collection (ING-04): fetch pages as evidence artifacts.

URL path: Scrapling HTTP Fetcher (no browser engine in v0.1) with a
stdlib robots.txt check before fetching; cleaned Markdown becomes the
artifact text and flows through the standard text-extraction pipeline.
Keyword path: Google News RSS -> top URLs -> same fetch pipeline.
"""

import re
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

USER_AGENT = "SUTRAM-Forensics-OSINT/0.2 (+forensics research tool)"
FETCH_TIMEOUT = 15
NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


class OsintFetchError(Exception):
    """A fetch failed in a way the API should report as HTTP 422."""


def _robots_allowed(url: str) -> bool:
    """True unless the site's robots.txt disallows our user-agent.

    Fail-open when robots.txt itself is unreachable: an unreadable
    robots.txt cannot disallow anything.
    """
    parts = urllib.parse.urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace").splitlines()
    except Exception:
        return True
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(body)
    return rp.can_fetch(USER_AGENT, url)


def fetch_url(url: str) -> dict:
    """Fetch one URL -> {markdown, final_url}. Raises OsintFetchError.

    Redirects are resolved first so the robots.txt check targets the true
    host; the resolved URL is then fetched with the HTTP Fetcher.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise OsintFetchError(f"unsupported URL (need http/https): {url[:80]}")
    final_url = _resolve_final_url(url)
    if not _robots_allowed(final_url):
        raise OsintFetchError(
            f"blocked by robots.txt: {urllib.parse.urlsplit(final_url).netloc}"
        )

    from scrapling.fetchers import Fetcher

    try:
        page = Fetcher.get(
            final_url,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
    except Exception as exc:
        raise OsintFetchError(f"fetch failed ({type(exc).__name__}): {exc}") from exc

    status = getattr(page, "status", 0) or 0
    if status >= 400:
        raise OsintFetchError(f"HTTP {status} fetching {url[:80]}")
    try:
        markdown = page.markdown()
    except Exception as exc:
        raise OsintFetchError(f"could not extract page text: {exc}") from exc
    if not (markdown or "").strip():
        raise OsintFetchError("page yielded no extractable text")
    return {"markdown": markdown.strip(), "final_url": getattr(page, "url", final_url)}


def _resolve_final_url(url: str, timeout: int = 10) -> str:
    """Follow redirects to the final URL (used for news.google.com article
    links, which 302 to the publisher). Returns the original on any failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:
        return url


def search_news(keyword: str, limit: int = 5) -> list[str]:
    """Google News RSS search -> resolved article URLs. Raises OsintFetchError."""
    rss_url = NEWS_RSS.format(q=urllib.parse.quote_plus(keyword))
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        raise OsintFetchError(f"news search unavailable: {exc}") from exc
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise OsintFetchError(f"news search returned bad XML: {exc}") from exc
    urls = []
    for item in root.iter("item"):
        link = item.findtext("link")
        if link and link.strip() not in urls:
            urls.append(link.strip())
        if len(urls) >= limit:
            break
    if not urls:
        raise OsintFetchError(f"news search returned no results for {keyword!r}")
    return urls


def slug_filename(url: str) -> str:
    """Derive a filesystem-safe filename from a URL."""
    parts = urllib.parse.urlsplit(url)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", parts.netloc + parts.path).strip("-")
    return (slug[:80] or "page") + ".md"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
