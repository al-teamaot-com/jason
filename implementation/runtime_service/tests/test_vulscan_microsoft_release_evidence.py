from datetime import date, datetime, timezone

import pytest

from jason_runtime.vulscan_microsoft_release_evidence import (
    GovernedMicrosoftReleaseRecord, MicrosoftPatchEvidenceUnavailable,
    normalize_governed_microsoft_release,
)

RELEASE = date(2026, 10, 13)
FETCHED = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def record(**kw):
    fields = dict(
        kb="KB5126653", release_date=RELEASE,
        release_source_url="https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
        release_source_verified=True, fetched_at=FETCHED,
        title="October 13, 2026 - KB5126653 (OS Build 22631.7652)",
        article_url="https://support.microsoft.com/en-us/servicing/os/windows-11/2026/10/kb5126653-windows-11-23h2-security-update",
        article_verified=True,
        summary="Windows cumulative security update.",
        known_issues="Published known issues were reviewed.",
        article_heading_release_date=RELEASE,
        revision_date=date(2026, 10, 16),
    )
    fields.update(kw)
    return GovernedMicrosoftReleaseRecord(**fields)


def test_later_revision_preserves_initial_release_clock():
    meta = normalize_governed_microsoft_release(
        record(), expected_kb="KB5126653")
    assert meta.release_date == RELEASE
    assert meta.revision_date == date(2026, 10, 16)
    assert meta.url.startswith("https://support.microsoft.com/")


def test_unverified_article_does_not_invent_description_or_known_issues():
    meta = normalize_governed_microsoft_release(record(
        article_verified=False, article_url=None), expected_kb="KB5126653")
    assert meta.source_verified is True
    assert meta.summary == ""
    assert meta.known_issues is None
    assert meta.url is None


@pytest.mark.parametrize("changes", [
    dict(release_source_verified=False),
    dict(release_source_url="https://learn.microsoft.com.evil.example/en-us/windows/release-health/windows11"),
    dict(release_source_url="http://learn.microsoft.com/en-us/windows/release-health/windows11"),
    dict(article_url="https://support.microsoft.com.evil.example/help/5126653"),
    dict(article_url="https://support.microsoft.com/help/5129999"),
    dict(article_heading_release_date=date(2026, 10, 16)),
])
def test_invalid_or_conflicting_official_source_rejected(changes):
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        normalize_governed_microsoft_release(
            record(**changes), expected_kb="KB5126653")


def test_wrong_kb_cannot_borrow_other_patch_documentation():
    with pytest.raises(MicrosoftPatchEvidenceUnavailable):
        normalize_governed_microsoft_release(
            record(), expected_kb="KB5127646")
