from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from connectors.microsoft_graph.aot_document_policy import (
    ApprovedAotDocumentGrant,
    AotExactDocumentReleasePolicy,
)

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)
TENANT = "aot-tenant"
PRINCIPAL = "jason-kfs-evidence-service"


def approved():
    grant = ApprovedAotDocumentGrant(
        principal_id=PRINCIPAL,
        microsoft_tenant_id=TENANT,
        site_id="aot-admin",
        drive_id="copier-logs",
        item_id="log-123",
        operations=frozenset({
            "knowledge.document.metadata.read",
            "knowledge.document.content.read",
        }),
        expires_at=NOW + timedelta(days=30),
    )
    return grant, AotExactDocumentReleasePolicy(
        frozenset({grant}), now=lambda: NOW,
    )


def call(policy, **overrides):
    values = {
        "principal_id": PRINCIPAL,
        "organization_id": "aot",
        "client_id": None,
        "tenant_id": TENANT,
        "operation": "knowledge.document.content.read",
        "site_id": "aot-admin",
        "drive_id": "copier-logs",
        "item_id": "log-123",
    }
    values.update(overrides)
    return policy.authorized(**values)


def test_only_exact_granted_file_is_readable():
    _, policy = approved()
    assert call(policy) is True
    assert call(policy, operation="knowledge.document.metadata.read") is True


@pytest.mark.parametrize("override", [
    {"principal_id": "user-1"},
    {"organization_id": "other-org"},
    {"client_id": "client-1"},
    {"tenant_id": "other-tenant"},
    {"site_id": "another-aot-site"},
    {"drive_id": "other-library"},
    {"item_id": "other-file"},
    {"item_id": None},
    {"operation": "knowledge.document.search"},
    {"operation": "knowledge.library.search"},
])
def test_doc_scope_does_not_expand_implicitly(override):
    _, policy = approved()
    assert call(policy, **override) is False


def test_expired_grant_denies_access():
    grant, _ = approved()
    policy = AotExactDocumentReleasePolicy(
        frozenset({replace(grant, expires_at=NOW-timedelta(seconds=1))}),
        now=lambda: NOW,
    )
    assert call(policy) is False


def test_no_grants_is_deny_all():
    policy = AotExactDocumentReleasePolicy(frozenset(), now=lambda: NOW)
    assert call(policy) is False


@pytest.mark.parametrize("kwargs", [
    {"principal_id": "*"},
    {"site_id": "*"},
    {"drive_id": ""},
    {"operations": frozenset({"knowledge.library.search"})},
    {"source_classification": "unrestricted"},
    {"expires_at": NOW.replace(tzinfo=None)},
])
def test_overbroad_or_invalid_release_grants_rejected(kwargs):
    grant, _ = approved()
    with pytest.raises(ValueError):
        replace(grant, **kwargs)
