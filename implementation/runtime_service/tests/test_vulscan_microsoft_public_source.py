from dataclasses import dataclass

import pytest

from jason_runtime.vulscan_microsoft_release_evidence import (
    MicrosoftPatchEvidenceUnavailable, normalize_governed_microsoft_release,
)
from jason_runtime.vulscan_microsoft_public_source import (
    BoundedOfficialMicrosoftHTTP,
    GovernedMicrosoftKBReleaseReader,
    OfficialMicrosoftFetchedDocument,
    WINDOWS_RELEASE_SOURCES, _MicrosoftRedirectsOnly,
)

KB = "KB5127648"
ARTICLE = "https://support.microsoft.com/help/5127648"
HISTORY = """<table><tr><th>Servicing option</th><th>Update type</th>
<th>Availability date</th><th>Build</th><th>KB article</th></tr>
<tr><td>General Availability Channel</td><td>2026-10 B</td>
<td>2026-10-13</td><td>26300.9711</td>
<td><a href="https://support.microsoft.com/help/5127648">KB5127648</a></td></tr>
</table>"""
ARTICLE_HTML = """<html><head><title>October 13, 2026 - KB5127648 Windows</title>
<meta name="description" content="Addresses Windows security problems."></head></html>"""


class FakeOfficialTransport:
    def __init__(self):
        self.calls = []

    def fetch(self, url, *, kb=None):
        self.calls.append((url, kb))
        if url == WINDOWS_RELEASE_SOURCES[0]:
            return OfficialMicrosoftFetchedDocument(HISTORY, url, url, True)
        if url == ARTICLE and kb == KB:
            return OfficialMicrosoftFetchedDocument(ARTICLE_HTML, url, url, True)
        raise MicrosoftPatchEvidenceUnavailable("not present in this OS history")


def test_read_permission_precedes_all_network_access():
    transport = FakeOfficialTransport()
    reader = GovernedMicrosoftKBReleaseReader(transport, lambda: False)
    with pytest.raises(PermissionError):
        reader(KB)
    assert transport.calls == []


def test_validated_official_sources_normalize_to_exact_kb_record():
    transport = FakeOfficialTransport()
    reader = GovernedMicrosoftKBReleaseReader(transport, lambda: True)
    record = reader(KB)
    meta = normalize_governed_microsoft_release(record, expected_kb=KB)
    assert meta.release_date.isoformat() == "2026-10-13"
    assert meta.url == ARTICLE
    assert meta.summary == "Addresses Windows security problems."
    assert len(transport.calls) == len(WINDOWS_RELEASE_SOURCES) + 1


def test_transport_rejects_user_supplied_urls_and_private_network_hosts():
    transport = BoundedOfficialMicrosoftHTTP()
    for url in ("https://127.0.0.1/", "http://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
                "https://learn.microsoft.com.evil.test/en-us/windows/release-health/windows11-release-information",
                "https://support.microsoft.com/help/5127648"):
        with pytest.raises(MicrosoftPatchEvidenceUnavailable):
            transport.fetch(url)
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        transport.fetch("https://support.microsoft.com/help/5129999", kb=KB)


def test_redirect_is_not_allowed_to_escape_verified_microsoft_hosts():
    h = _MicrosoftRedirectsOnly(kb=KB)
    class Request:
        full_url = ARTICLE
    for target in ("http://support.microsoft.com/help/5127648",
                   "https://example.com/help/5127648",
                   "https://169.254.169.254/latest/meta-data/",
                   "https://support.microsoft.com.evil.test/help/5127648"):
        with pytest.raises(MicrosoftPatchEvidenceUnavailable):
            h.redirect_request(Request(), None, 302, "Moved", {}, target)


def test_conflicting_official_histories_fail_closed():
    transport = FakeOfficialTransport()
    original = transport.fetch
    def conflict(url, *, kb=None):
        if url == WINDOWS_RELEASE_SOURCES[1]:
            return OfficialMicrosoftFetchedDocument(
                HISTORY.replace("2026-10-13", "2026-10-14"), url, url, True)
        return original(url, kb=kb)
    transport.fetch = conflict
    with pytest.raises(MicrosoftPatchEvidenceUnavailable, match="conflicting"):
        GovernedMicrosoftKBReleaseReader(transport, lambda: True)(KB)


def test_unknown_kb_cannot_borrow_other_microsoft_update_date():
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        GovernedMicrosoftKBReleaseReader(
            FakeOfficialTransport(), lambda: True)("KB5129001")


def test_article_unavailable_degrades_description_without_fake_details():
    transport = FakeOfficialTransport()
    original = transport.fetch
    def fail_article(url, *, kb=None):
        if kb is not None:
            raise MicrosoftPatchEvidenceUnavailable("article unavailable")
        return original(url, kb=kb)
    transport.fetch = fail_article
    record = GovernedMicrosoftKBReleaseReader(transport, lambda: True)(KB)
    assert record.article_verified is False
    assert record.summary == ""
    assert record.known_issues is None
