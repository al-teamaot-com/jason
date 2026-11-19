"""Exact native systemd Stage E source binding must never impersonate Compose."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet

CANDIDATE = "b" * 40
ROLLBACK = "a" * 40


def good():
    return contract.draft(candidate_sha=CANDIDATE, rollback_sha=ROLLBACK)


def test_exact_manifest_is_typed_systemd_not_a_compose_masquerade():
    result = good()
    m = result["manifest"]
    assert m["release_mode"] == "owner-signed-native-systemd-stage-e"
    assert m["action"] == packet.ACTION
    assert m["release_class"] == "high-risk"
    assert m["rollback_sha"] == ROLLBACK
    assert m["provider_scope"]["provider"] == "none"
    assert "compose_project" not in m
    assert "compose_sha256" not in m
    assert "image_digest" not in m
    assert result["status"].endswith("no_production_authority")
    assert result["source_files_verified"] == len(packet.REVIEWED_PATHS)
    assert result["production_release_ready"] is False
    assert result["approved_root_bootstrap"] is False
    assert result["root_accepted"] is False
    assert result["signed_owner_proof"] is None


def test_deterministic_manifest_and_scope_bytes():
    a, b = good(), good()
    assert a == b
    assert a["manifest_sha256"] == contract.sha256(
        packet.canonical(a["manifest"])).hexdigest()
    assert contract.validate(a["manifest"], a["source_scope"]) == {
        key: value for key, value in a.items()
        if key not in {"manifest", "source_scope", "signed_owner_proof",
                       "approved_root_bootstrap"}
    }


@pytest.mark.parametrize("key,value", [
    ("release_mode", "owner-signed-independent-compose"),
    ("action", "generic-release"),
    ("repository", "other-org/jason"),
    ("release_class", "fast"),
    ("component_id", "jason-unreviewed"),
    ("requires_root_preflight", False),
    ("requires_signed_owner", False),
    ("standing_authority", True),
    ("protected_restart_allowed", True),
    ("production_freeze_override", True),
    ("provider_scope", {"provider": "autotask"}),
    ("protected_services", []),
    ("freeze_sha256", "0" * 64),
    ("prior_root_policy_sha256", "0" * 64),
    ("source_scope_sha256", "0" * 64),
    ("source_manifest_sha256", "0" * 64),
    ("source_candidate_policy_sha256", "0" * 64),
    ("new_systemd_file_count", 11),
    ("legacy_source_input_count", 11),
    ("reviewed_file_count", 47),
    ("rollback_sha", "b" * 40),
    ("candidate_sha", "not-a-sha"),
])
def test_unreviewed_manifest_field_or_authority_is_denied(key, value):
    d = good()
    m = deepcopy(d["manifest"])
    m[key] = value
    with pytest.raises(contract.StageEManifestDenied):
        contract.validate(m, d["source_scope"])


def test_extra_manifest_field_and_omitted_field_denied():
    d = good()
    m = deepcopy(d["manifest"])
    m["unexpected"] = 1
    with pytest.raises(contract.StageEManifestDenied, match="UNREVIEWED_FIELDS"):
        contract.validate(m, d["source_scope"])
    del m["unexpected"]
    del m["requires_signed_owner"]
    with pytest.raises(contract.StageEManifestDenied, match="UNREVIEWED_FIELDS"):
        contract.validate(m, d["source_scope"])


@pytest.mark.parametrize("key,value", [
    ("retire_user", []),
    ("retire_root", []),
    ("add_user", []),
    ("add_root", []),
    ("protected_runtime_mcp_restart_allowed", True),
    ("provider_writes_allowed", True),
    ("production_freeze_override_allowed", True),
    ("exact_replacement_files_sha256", {}),
    ("action", "an-unreviewed-action"),
])
def test_source_scope_cannot_be_rebound(key, value):
    d = good()
    scope = deepcopy(d["source_scope"])
    scope[key] = value
    with pytest.raises(contract.StageEManifestDenied):
        contract.validate(d["manifest"], scope)


def test_source_scope_additional_keys_denied():
    d = good()
    scope = deepcopy(d["source_scope"])
    scope["allow_unsafe_root"] = True
    with pytest.raises(contract.StageEManifestDenied):
        contract.validate(d["manifest"], scope)


def test_invalid_candidate_and_rollback_fail_closed_before_returning_draft():
    for candidate, rollback in (
        ("a" * 40, "a" * 40),
        ("not-valid", "a" * 40),
        ("a" * 40, "not-valid"),
    ):
        with pytest.raises(packet.StageEReleasePacketDenied):
            contract.draft(candidate_sha=candidate, rollback_sha=rollback)
