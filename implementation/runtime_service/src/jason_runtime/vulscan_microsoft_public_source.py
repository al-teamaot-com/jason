"""Bounded, allowlisted public Microsoft KB reader for VulScan V2.

This adapter performs only GET requests to Microsoft Learn release-history and
Support KB pages. It never accesses the Datto/Autotask APIs, credentials or
internal tenant services. It is NOT registered into production composition;
the caller must provide an existing approved read-authority check.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .vulscan_microsoft_release_evidence import (
    GovernedMicrosoftReleaseRecord, MicrosoftPatchEvidenceUnavailable,
)
from .vulscan_microsoft_release_html import (
    build_governed_microsoft_record, parse_verified_microsoft_release_history,
)
from .vulscan_patch_approval_notification import verified_microsoft_kb_url

WINDOWS_RELEASE_SOURCES = (
    "https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
    "https://learn.microsoft.com/en-us/windows/release-health/release-information",
    "https://learn.microsoft.com/en-us/windows/release-health/windows-server-release-info",
)
_MAX_DOCUMENT_BYTES = 4_000_000
_KB = re.compile(r"KB[0-9]{5,9}\Z")


def _permitted_url(url: str, *, kb: str | None = None) -> bool:
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname
                or parts.port not in (None, 443)
                or parts.username is not None or parts.password is not None
                or parts.fragment):
            return False
        if kb is None:
            return url in WINDOWS_RELEASE_SOURCES
        return verified_microsoft_kb_url(kb, url)
    except (ValueError, TypeError):
        return False


class _MicrosoftRedirectsOnly(HTTPRedirectHandler):
    def __init__(self, *, kb: str | None):
        self.kb = kb

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        target = urljoin(req.full_url, newurl)
        if not _permitted_url(target, kb=self.kb):
            raise MicrosoftPatchEvidenceUnavailable("Microsoft read redirect left approved source scope")
        return Request(target, headers={"Accept": "text/html", "Accept-Encoding": "identity"},
                       method="GET")


@dataclass(frozen=True, slots=True)
class OfficialMicrosoftFetchedDocument:
    body: str
    requested_url: str
    final_url: str
    source_verified: bool


class BoundedOfficialMicrosoftHTTP:
    """TLS-verified public HTTPS, no credentials and no off-scope redirects."""

    def fetch(self, url: str, *, kb: str | None = None) -> OfficialMicrosoftFetchedDocument:
        if not _permitted_url(url, kb=kb):
            raise MicrosoftPatchEvidenceUnavailable("Microsoft read URL not allowlisted")
        opener = build_opener(_MicrosoftRedirectsOnly(kb=kb))
        request = Request(url, headers={
            "User-Agent": "Project-Jason-VulScan-ReadOnly/1.0",
            "Accept": "text/html",
            "Accept-Encoding": "identity",
        }, method="GET")
        try:
            with opener.open(request, timeout=12) as response:
                final_url = response.geturl()
                if not _permitted_url(final_url, kb=kb):
                    raise MicrosoftPatchEvidenceUnavailable("Microsoft final URL outside approved scope")
                ctype = str(response.headers.get("Content-Type") or "").lower()
                if "text/html" not in ctype:
                    raise MicrosoftPatchEvidenceUnavailable("Microsoft source not HTML")
                raw = response.read(_MAX_DOCUMENT_BYTES + 1)
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            raise MicrosoftPatchEvidenceUnavailable(
                "Microsoft public documentation unavailable"
            ) from exc
        if not raw or len(raw) > _MAX_DOCUMENT_BYTES:
            raise MicrosoftPatchEvidenceUnavailable("Microsoft document missing or over limit")
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MicrosoftPatchEvidenceUnavailable("Microsoft document is not UTF-8") from exc
        return OfficialMicrosoftFetchedDocument(
            body=body, requested_url=url, final_url=final_url,
            source_verified=True,
        )


@dataclass
class GovernedMicrosoftKBReleaseReader:
    """Existing read-grant check + strictly bounded official-source fetch."""

    transport: BoundedOfficialMicrosoftHTTP
    can_read_official_public_docs: Callable[[], bool]

    def __call__(self, kb: str) -> GovernedMicrosoftReleaseRecord:
        if not _KB.fullmatch(kb):
            raise MicrosoftPatchEvidenceUnavailable("invalid exact KB")
        if self.can_read_official_public_docs() is not True:
            raise PermissionError("governed Microsoft KB public-read authority absent")

        # Sources are fixed and never constructed from ticket/client text.
        authoritative = []
        checked_at = datetime.now(timezone.utc)
        for source in WINDOWS_RELEASE_SOURCES:
            try:
                document = self.transport.fetch(source)
                if (not document.source_verified
                        or document.requested_url != source
                        or document.final_url != source):
                    raise MicrosoftPatchEvidenceUnavailable("release source provenance mismatch")
                released, article = parse_verified_microsoft_release_history(
                    document.body, kb=kb, source_url=source,
                    fetched_at=checked_at, transport_verified=True)
                authoritative.append((source, document.body, released, article))
            except MicrosoftPatchEvidenceUnavailable:
                # A KB may appear in a single Windows version family.
                continue
        if not authoritative:
            raise MicrosoftPatchEvidenceUnavailable("exact KB not in trusted Microsoft release history")
        if len({(date_, url) for _, _, date_, url in authoritative}) != 1:
            raise MicrosoftPatchEvidenceUnavailable("conflicting Microsoft Windows KB release evidence")
        source, release_html, _, article_url = authoritative[0]
        article_html = None
        try:
            article = self.transport.fetch(article_url, kb=kb)
            if (article.source_verified and article.requested_url == article_url
                    and _permitted_url(article.final_url, kb=kb)):
                article_html = article.body
        except MicrosoftPatchEvidenceUnavailable:
            # A verified release date remains useful, but do not invent article text.
            pass
        return build_governed_microsoft_record(
            kb=kb, release_html=release_html, article_html=article_html,
            release_url=source, fetched_at=checked_at,
            transport_verified=True,
        )
