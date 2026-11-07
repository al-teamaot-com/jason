from datetime import date, datetime, timezone

import pytest

from jason_runtime.vulscan_microsoft_release_evidence import (
    MicrosoftPatchEvidenceUnavailable, normalize_governed_microsoft_release,
)
from jason_runtime.vulscan_microsoft_release_html import (
    build_governed_microsoft_record, parse_verified_microsoft_release_history,
)

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
RELEASE_URL = (
    "https://learn.microsoft.com/en-us/windows/release-health/"
    "windows11-release-information"
)
ARTICLE = (
    "https://support.microsoft.com/en-us/topic/"
    "october-13-2026-kb5127648-os-build-26200-9711"
)


def history(*, first_date="2026-10-13", second_date="2026-10-13", url=ARTICLE):
    return f"""
    <html><body><table><thead><tr><th>Servicing option</th>
    <th>Update type</th><th>Availability date</th><th>Build</th>
    <th>KB article</th></tr></thead>
    <tbody>
    <tr><td>General Availability Channel</td><td>2026-10 B</td>
    <td>{first_date}</td><td>26200.9711</td>
    <td><a href="{url}">KB5127648</a></td></tr>
    <tr><td>General Availability Channel</td><td>2026-10 B</td>
    <td>{second_date}</td><td>26100.9711</td>
    <td><a href="{url}">KB5127648</a></td></tr>
    </tbody></table></body></html>
    """


def test_release_history_exact_kb_date_and_link():
    day, href = parse_verified_microsoft_release_history(
        history(), kb="KB5127648", source_url=RELEASE_URL,
        fetched_at=NOW, transport_verified=True)
    assert day == date(2026, 10, 13)
    assert href == ARTICLE


def test_article_summary_is_sourced_not_fabricated():
    article = ('<html><head><title>October 13, 2026 - '
               'KB5127648 Windows 11 Update</title>'
               '<meta name="description" content="Addresses security '
               'vulnerabilities in Windows 11."></head></html>')
    result = build_governed_microsoft_record(
        kb="KB5127648", release_html=history(),
        article_html=article, release_url=RELEASE_URL,
        fetched_at=NOW, transport_verified=True)
    meta = normalize_governed_microsoft_release(result, expected_kb="KB5127648")
    assert meta.release_date == date(2026, 10, 13)
    assert meta.summary == "Addresses security vulnerabilities in Windows 11."
    assert meta.url == ARTICLE
    assert meta.known_issues is None


@pytest.mark.parametrize("reason", [
    dict(first_date="2026-10-14"),
    dict(url="https://support.microsoft.com.evil.example/help/5127648"),
    dict(url="https://example.org/kb5127648"),
])
def test_conflicted_or_untrusted_vendor_rows_fail_closed(reason):
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        parse_verified_microsoft_release_history(
            history(**reason), kb="KB5127648",
            source_url=RELEASE_URL, fetched_at=NOW,
            transport_verified=True)


def test_source_must_be_tls_verified_and_official():
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        parse_verified_microsoft_release_history(
            history(), kb="KB5127648",
            source_url=RELEASE_URL, fetched_at=NOW,
            transport_verified=False)
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        parse_verified_microsoft_release_history(
            history(), kb="KB5127648",
            source_url="https://learn.microsoft.com.evil.example/windows/release-health",
            fetched_at=NOW, transport_verified=True)


def test_missing_exact_kb_cannot_borrow_another_kb_date():
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        parse_verified_microsoft_release_history(
            history(), kb="KB5127653", source_url=RELEASE_URL,
            fetched_at=NOW, transport_verified=True)


def test_source_article_title_mismatch_omits_unverified_description():
    result = build_governed_microsoft_record(
        kb="KB5127648", release_html=history(),
        article_html='<title>Other unrelated Microsoft support article</title>',
        release_url=RELEASE_URL, fetched_at=NOW, transport_verified=True)
    assert result.article_verified is False
    assert result.summary == ""
    assert result.article_url == ARTICLE
