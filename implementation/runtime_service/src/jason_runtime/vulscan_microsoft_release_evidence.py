"""Validate official Microsoft KB release evidence supplied by governed readers.

No HTTP, scraping, browser, or provider call occurs in this module.
The incoming record must originate from an independently authorized Microsoft
release-health/KB read. Do not convert search snippets into approved facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit

from .vulscan_patch_approval_notification import (
    MicrosoftKBMetadata, verified_microsoft_kb_url,
)


class MicrosoftPatchEvidenceUnavailable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GovernedMicrosoftReleaseRecord:
    kb: str
    release_date: date
    release_source_url: str
    release_source_verified: bool
    fetched_at: datetime
    title: str
    article_url: str | None = None
    article_verified: bool = False
    summary: str = ""
    known_issues: str | None = None
    article_heading_release_date: date | None = None
    # A later KB page revision is not the initial update availability date.
    revision_date: date | None = None


def _official_release_source(url: str, kb: str) -> bool:
    if not isinstance(url, str) or len(url) > 1000:
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.fragment):
            return False
        path = parsed.path.lower()
        return (
            (host == "learn.microsoft.com"
             and ("/windows/release-health/" in path
                  or "/windows-server/" in path))
            or (host == "support.microsoft.com"
                and verified_microsoft_kb_url(kb, url))
        )
    except ValueError:
        return False


def normalize_governed_microsoft_release(
    record: GovernedMicrosoftReleaseRecord, *, expected_kb: str,
) -> MicrosoftKBMetadata:
    """Use initial availability date, rejecting conflicting official evidence."""
    if (not isinstance(record, GovernedMicrosoftReleaseRecord)
            or record.kb.strip().upper() != expected_kb.upper()
            or record.release_source_verified is not True
            or not _official_release_source(record.release_source_url, expected_kb)
            or record.fetched_at.tzinfo is None):
        raise MicrosoftPatchEvidenceUnavailable("official Microsoft release evidence missing")
    if (record.article_heading_release_date is not None
            and record.article_heading_release_date != record.release_date):
        raise MicrosoftPatchEvidenceUnavailable("KB heading and release-health dates conflict")
    if not record.title.strip() or len(record.title) > 500:
        raise MicrosoftPatchEvidenceUnavailable("Microsoft update title missing or oversized")
    article_url = None
    if record.article_verified:
        if not record.article_url or not verified_microsoft_kb_url(
                expected_kb, record.article_url):
            raise MicrosoftPatchEvidenceUnavailable("claimed verified KB URL is invalid")
        article_url = record.article_url

    return MicrosoftKBMetadata(
        kb=expected_kb.upper(),
        release_date=record.release_date,
        title=record.title,
        summary=record.summary if record.article_verified else "",
        known_issues=record.known_issues if record.article_verified else None,
        url=article_url,
        source_checked_at=record.fetched_at,
        source_verified=True,
        revision_date=record.revision_date,
    )
