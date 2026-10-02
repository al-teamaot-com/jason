from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from bootstrap.candidate_canary_authority import (
    CandidateCanaryAuthorityError,
    provision_candidate_canary_authority,
)
from bootstrap.candidate_host import CandidateHostIdentity
from kernel.identity_authority.durable import SQLiteIdentityAuthorityStore
from orchestrator.provider_health_canary_policy import (
    PROVIDER_HEALTH_CANARY_PRINCIPAL,
    enabled_provider_health_canary_specs,
    provider_health_canary_organization_id,
)


NOW = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def test_canary_policy_requires_explicit_organization_and_provider_set():
    with pytest.raises(ValueError, match="organization"):
        provider_health_canary_organization_id({})
    with pytest.raises(ValueError, match="provider set"):
        enabled_provider_health_canary_specs({})


def test_canary_policy_filters_only_explicit_providers():
    env = {
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID": "org-test",
        "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS": "autotask,datto_rmm",
    }
    assert provider_health_canary_organization_id(env) == "org-test"
    assert [item["provider_id"] for item in enabled_provider_health_canary_specs(env)] == [
        "autotask",
        "datto_rmm",
    ]


def test_candidate_canary_authority_is_observe_only_and_time_bounded(tmp_path):
    root = tmp_path / "candidate"
    receipt = provision_candidate_canary_authority(
        target_root=root,
        candidate_identity=identity(),
        organization_id="org-test",
        provider_ids=("autotask", "datto_rmm"),
        now=NOW,
        lifetime_minutes=45,
    )
    assert receipt.permission == "observe"
    assert receipt.approval_required is False
    assert receipt.provider_ids == ("autotask", "datto_rmm")
    assert len(receipt.grant_ids) == 2

    store = SQLiteIdentityAuthorityStore(
        root / "var/lib/jason/authority/authority.sqlite3"
    )
    try:
        record = store.get_identity(PROVIDER_HEALTH_CANARY_PRINCIPAL)
        assert record is not None
        assert record.organization_id == "org-test"
        grants = store.list_grants_for_subject(PROVIDER_HEALTH_CANARY_PRINCIPAL)
        assert len(grants) == 2
        assert {item.permission.value for item in grants} == {"observe"}
        assert all(item.effective_from == NOW for item in grants)
        assert all(item.effective_until is not None for item in grants)
    finally:
        store.close()


def test_conflicting_existing_canary_identity_fails_closed(tmp_path):
    root = tmp_path / "candidate"
    provision_candidate_canary_authority(
        target_root=root,
        candidate_identity=identity(),
        organization_id="org-one",
        provider_ids=("autotask",),
        now=NOW,
    )
    with pytest.raises(
        CandidateCanaryAuthorityError,
        match="identity conflicts",
    ):
        provision_candidate_canary_authority(
            target_root=root,
            candidate_identity=identity(),
            organization_id="org-two",
            provider_ids=("autotask",),
            now=NOW,
        )


def test_unknown_provider_and_excessive_lifetime_fail_closed(tmp_path):
    with pytest.raises(CandidateCanaryAuthorityError, match="unsupported"):
        provision_candidate_canary_authority(
            target_root=tmp_path / "candidate",
            candidate_identity=identity(),
            organization_id="org-test",
            provider_ids=("unknown-provider",),
            now=NOW,
        )
    with pytest.raises(CandidateCanaryAuthorityError, match="lifetime"):
        provision_candidate_canary_authority(
            target_root=tmp_path / "candidate",
            candidate_identity=identity(),
            organization_id="org-test",
            provider_ids=("autotask",),
            now=NOW,
            lifetime_minutes=1440,
        )


def test_mcp_canary_source_uses_explicit_organization():
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "implementation/mcp_service/src/jason_mcp/provider_health_canary.py"
    ).read_text(encoding="utf-8")
    assert 'organization_id="aot"' not in source
    assert "provider_health_canary_organization_id()" in source
    assert "enabled_provider_health_canary_specs()" in source

def test_mcp_canary_admin_has_no_aot_organization_or_all_provider_static_scope():
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "implementation/mcp_service/src/jason_mcp/server.py"
    ).read_text(encoding="utf-8")
    start = source.index("def _provider_health_canary_grant_ids")
    end = source.index("def list_exact_authority_grants", start)
    canary_region = source[start:end]
    assert 'organization != "aot"' not in canary_region
    assert "provider_health_canary_organization_id()" in canary_region
    assert "enabled_provider_health_canary_specs()" in canary_region
