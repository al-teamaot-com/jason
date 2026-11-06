"""Fault-injection regression of 2026-10-27 release/rollback authorization.

All tests are isolated: no Docker mutation, no root policy writes, no provider
network, no credential lookup or customer data.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))


def load(name: str, filename: str):
    source = ROOT / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manager = load("p0_rollback_profile_manager", "release_manager_host_runner.py")
host = load("p0_rollback_root_host", "release_host_reconcile_worker.py")
root_control = load("p0_rollback_root_control", "release_control_transition_worker.py")

OLD = "8" * 40
NEW = "2" * 40
MIGRATED = "1" * 40
UNRELATED = "e" * 40
V10 = "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10"
V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"


def lkg(revision):
    return {
        "complete": True, "revision": revision,
        "runtime_revision": revision, "runtime_image_id": "sha256:" + ("a" if revision == OLD else "b") * 64,
        "mcp_revision": revision, "mcp_image_id": "sha256:" + ("c" if revision == OLD else "d") * 64,
        "host_revision": revision, "host_release": "/opt/jason/releases/" + revision,
        "release_manager_source_revision": revision,
        "desired_state_policy_digest": "sha256:" + "f" * 64,
        "scheduled_control_units": {"jason-release-manager.timer": "active"},
    }


def test_exact_profile_rollback_never_supplies_old_profile_as_candidate_override():
    original = {
        "JASON_SOURCE_REVISION_OVERRIDE": OLD,
        "JASON_RUNTIME_PRODUCTION_IMAGE": "jason-runtime:rollback-current",
        "JASON_MCP_PRODUCTION_IMAGE": "jason-mcp:rollback-current",
        "JASON_PROVIDER_READ_ACTIVATION_PROFILE": V11,
    }
    corrected = manager.autotask_rollback_environment(
        original, prior_autotask_profile=V10
    )
    assert "JASON_PROVIDER_READ_ACTIVATION_PROFILE" not in corrected
    assert corrected["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] == V10
    assert corrected["JASON_SOURCE_REVISION_OVERRIDE"] == OLD
    assert corrected["JASON_MCP_PRODUCTION_IMAGE"].endswith(":rollback-current")
    assert original["JASON_PROVIDER_READ_ACTIVATION_PROFILE"] == V11


@pytest.mark.parametrize("profile", ["", "not-approved", V10 + "-typo"])
def test_rollback_profile_rejects_unknown_authority(profile):
    with pytest.raises(manager.ReleaseManagerError, match="unsupported"):
        manager.autotask_rollback_environment({}, prior_autotask_profile=profile)


def test_immutable_root_transition_retains_previous_complete_lkg(tmp_path):
    records = tmp_path / "records"
    records.mkdir()
    record = {
        "state": "production",
        "owner_approval": {"approved": True, "candidate_sha": NEW},
    }
    (records / ("release-" + NEW[:16] + ".json")).write_text(json.dumps(record))
    last = {"release_id": "release-" + OLD[:16], "manifest": lkg(OLD), "recorded_at": "before"}
    control = {
        "schema_version": "1.0",
        "last_known_good": last,
        "circuit_breaker": {"state": "closed"},
    }
    with (
        patch.object(root_control, "ROOT", tmp_path),
        patch.object(root_control, "verify_drift"),
        patch.object(root_control, "verify_health", return_value=lkg(NEW)),
    ):
        result = root_control.apply_transition({
            "action": "set_last_known_good",
            "release_id": "release-" + NEW[:16],
            "revision": NEW,
        }, control)
    assert result["last_known_good"]["manifest"] == lkg(NEW)
    assert result["previous_last_known_good"] == last
    assert result["circuit_breaker"]["state"] == "closed"


@pytest.mark.parametrize("incomplete_previous", [False, True])
def test_root_only_previous_baseline_is_stored_only_when_complete(tmp_path, incomplete_previous):
    records = tmp_path / "records"
    records.mkdir()
    (records / ("release-" + NEW[:16] + ".json")).write_text(
        json.dumps({"state": "closed", "owner_approval": {"approved": True, "candidate_sha": NEW}})
    )
    previous = lkg(OLD)
    if incomplete_previous:
        previous["complete"] = False
    control = {"schema_version": "1.0", "last_known_good": {"manifest": previous}}
    with (
        patch.object(root_control, "ROOT", tmp_path),
        patch.object(root_control, "verify_drift"),
        patch.object(root_control, "verify_health", return_value=lkg(NEW)),
    ):
        output = root_control.apply_transition({
            "action": "set_last_known_good",
            "release_id": "release-" + NEW[:16],
            "revision": NEW,
        }, control)
    assert ("previous_last_known_good" in output) is not incomplete_previous


def _root_previous_probe(*, target=OLD, prev_revision=OLD, prev_complete=True,
                         current=NEW, breaker="open", digest_matches=True,
                         ancestry=True, receipt_phase="applied"):
    control = {
        "schema_version": "1.0",
        "last_known_good": {"manifest": lkg(current)},
        "previous_last_known_good": {"manifest": {**lkg(prev_revision), "complete": prev_complete}},
        "circuit_breaker": {"state": breaker},
    }
    receipt = {
        "candidate_sha": MIGRATED,
        "rollback_sha": "0" * 40,
        "phase": receipt_phase,
        "applied_sha256": "trusted-policy-digest",
    }
    policy_bytes = b"canonical root-owned signed migration"
    helper = SimpleNamespace(
        ACTIVE=Path("/root/active-migration.json"),
        ROOT=Path("/root/protected-release"),
        POLICY=Path("/root/policy.json"),
        _json=lambda raw: json.loads(raw),
        _root_only=lambda p: (
            json.dumps(receipt).encode() if p.name == "active-migration.json"
            else json.dumps(control).encode() if p.name == "production-control-state.json"
            else policy_bytes
        ),
        digest=lambda raw: "trusted-policy-digest" if digest_matches else "tampered",
    )
    with (
        patch.object(host, "_trusted_root_policy_helper", return_value=helper),
        patch.object(host, "_verified_migration_ancestor", return_value=ancestry),
        patch.object(Path, "is_file", return_value=True),
    ):
        return host._restore_root_policy_for_target(target)


def test_open_breaker_can_restore_only_root_owned_previous_exact_lkg():
    assert _root_previous_probe() == "PREVIOUS_MIGRATION_LKG_VERIFIED"


@pytest.mark.parametrize("changes", [
    {"target": UNRELATED},
    {"prev_revision": UNRELATED},
    {"prev_complete": False},
    {"digest_matches": False},
    {"ancestry": False},
    {"receipt_phase": "unapplied"},
])
def test_open_breaker_refuses_any_unproven_ancestor_or_tampered_policy(changes):
    with pytest.raises(host.HostReconcileError, match="does not belong|differs"):
        _root_previous_probe(**changes)


def test_native_runtime_rollback_waits_for_healthy_before_verification():
    source = (ROOT / "tools/release_manager_host_runner.py").read_text()
    section = source[source.index("if runtime_attempted:", source.index("except Exception as error:")):]
    waited = section.index("wait_live_runtime()")
    verified = section.index('rollback_surface_is_verified("runtime", rollback_sha, baseline_manifest)', waited)
    assert waited < verified
