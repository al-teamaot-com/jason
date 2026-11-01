"""Parse trusted Microsoft Windows release-history HTML into bounded KB evidence.

This is a *provider-side* parser, not a standalone web client or an authority
grant. Only call it with bytes retrieved by a separately authorized, HTTPS-
verified Microsoft source connector. Never use search snippets as input.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from .vulscan_microsoft_release_evidence import (
    GovernedMicrosoftReleaseRecord, MicrosoftPatchEvidenceUnavailable,
)
from .vulscan_patch_approval_notification import verified_microsoft_kb_url

_KB = re.compile(r"^KB[0-9]{5,9}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_RELEASE = {
    "https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
    "https://learn.microsoft.com/en-us/windows/release-health/release-information",
    "https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info",
}
_MAX_HTML = 4_000_000


class _ReleaseTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self._row = False
        self._cell = False
        self._cells: list[str] = []
        self._links: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = True
            self._cells = []
            self._links = []
        elif tag in ("td", "th") and self._row:
            self._cell = True
            self._parts = []
        elif tag == "a" and self._cell:
            url = dict(attrs).get("href")
            if isinstance(url, str):
                self._links.append(url)

    def handle_data(self, data):
        if self._cell:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell:
            self._cells.append(" ".join(" ".join(self._parts).split()))
            self._cell = False
        elif tag == "tr" and self._row:
            if self._cells:
                self.rows.append((tuple(self._cells), tuple(self._links)))
            self._row = False


def parse_verified_microsoft_release_history(
    html: str, *, kb: str, source_url: str, fetched_at: datetime,
    transport_verified: bool,
) -> tuple[date, str]:
    """Return initial availability date and exact official KB article URL.

    It is not a date guessing algorithm. Reject duplicated KB rows with
    contradictory dates or unknown/changed HTML structures.
    """
    if (transport_verified is not True or source_url not in _ALLOWED_RELEASE
            or fetched_at.tzinfo is None or not _KB.fullmatch(kb)
            or not isinstance(html, str) or not 0 < len(html) <= _MAX_HTML):
        raise MicrosoftPatchEvidenceUnavailable("trusted Microsoft release history unavailable")
    parsed = _ReleaseTable()
    parsed.feed(html)
    matches: set[tuple[date, str]] = set()
    for cells, links in parsed.rows:
        if len(cells) < 5 or not _DATE.fullmatch(cells[2]):
            continue
        if not re.search(r"(?<![0-9])" + re.escape(kb[2:]) + r"(?![0-9])",
                         cells[-1], flags=re.I):
            continue
        try:
            published = date.fromisoformat(cells[2])
        except ValueError:
            continue
        valid_links = [
            urljoin(source_url, href) for href in links
            if verified_microsoft_kb_url(kb, urljoin(source_url, href))
        ]
        if len(set(valid_links)) != 1:
            raise MicrosoftPatchEvidenceUnavailable("matching KB article link not unambiguous")
        matches.add((published, valid_links[0]))
    if not matches:
        raise MicrosoftPatchEvidenceUnavailable("KB/date absent from verified Microsoft release table")
    dates = {day for day, _ in matches}
    urls = {url for _, url in matches}
    if len(dates) != 1 or len(urls) != 1:
        raise MicrosoftPatchEvidenceUnavailable("conflicting Microsoft KB dates or article links")
    return next(iter(dates)), next(iter(urls))


class _OfficialArticle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.description: str = ""
        self._inside_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._inside_title = True
        elif tag == "meta":
            data = dict(attrs)
            if str(data.get("name") or "").lower() == "description":
                self.description = str(data.get("content") or "")[:550]

    def handle_data(self, text):
        if self._inside_title:
            self.title.append(text)

    def handle_endtag(self, tag):
        if tag == "title":
            self._inside_title = False


def build_governed_microsoft_record(
    *, kb: str, release_html: str, article_html: str | None,
    release_url: str, fetched_at: datetime, transport_verified: bool,
) -> GovernedMicrosoftReleaseRecord:
    released, article_url = parse_verified_microsoft_release_history(
        release_html, kb=kb, source_url=release_url,
        fetched_at=fetched_at, transport_verified=transport_verified)
    title = f"Microsoft Windows update {kb}"
    description = ""
    article_verified = False
    if article_html is not None:
        if not isinstance(article_html, str) or len(article_html) > _MAX_HTML:
            raise MicrosoftPatchEvidenceUnavailable("Microsoft article HTML oversized")
        parsed = _OfficialArticle()
        parsed.feed(article_html)
        article_title = " ".join(" ".join(parsed.title).split())
        # No fabricated Microsoft description if the verified article title
        # cannot be tied to the exact KB.
        if kb.casefold() in article_title.casefold():
            title = article_title[:400]
            description = " ".join(parsed.description.split())[:420]
            article_verified = True
    return GovernedMicrosoftReleaseRecord(
        kb=kb, release_date=released, release_source_url=release_url,
        release_source_verified=transport_verified,
        fetched_at=fetched_at, title=title,
        article_url=article_url, article_verified=article_verified,
        summary=description, known_issues=None,
        article_heading_release_date=released,
    )
