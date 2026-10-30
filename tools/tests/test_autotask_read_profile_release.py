"""Autotask provider-read profile promotion is source-bound and rollback-safe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_release_manager_host_runner import runner

V10 = "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10"
V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"


def test_candidate_profile_loaded_from_immutable_source(tmp_path):
    path = tmp_path / "config" / "autotask-entity-read-profile.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"schema_version": "1.0", "read_profile": V11, "rollback_read_profile": V10}))
    assert runner.declared_autotask_read_profile(tmp_path) == V11


@pytest.mark.parametrize("payload", [
    {"schema_version": "1.0", "read_profile": "invalid", "rollback_read_profile": V10},
    {"schema_version": "1.0", "read_profile": V11, "rollback_read_profile": "invalid"},
    {"schema_version": "2.0", "read_profile": V11, "rollback_read_profile": V10},
    {"schema_version": "1.0", "read_profile": V11, "rollback_read_profile": V10, "extra": "ignored"},
    {"read_profile": V11}, [],
])
def test_unapproved_or_bad_profile_declaration_fails_closed(tmp_path, payload):
    path = tmp_path / "config" / "autotask-entity-read-profile.json"
    path.parent.mkdir()
    path.write_text(json.dumps(payload))
    with pytest.raises(runner.ReleaseManagerError, match="Autotask.*declaration invalid"):
        runner.declared_autotask_read_profile(tmp_path)


def test_missing_legacy_declaration_does_not_force_new_profile(tmp_path):
    assert runner.declared_autotask_read_profile(tmp_path) is None


def test_symlink_profile_source_is_refused(tmp_path):
    data = tmp_path / "outside.json"
    data.write_text(json.dumps({"schema_version": "1.0", "read_profile": V11, "rollback_read_profile": V10}))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "autotask-entity-read-profile.json").symlink_to(data)
    with pytest.raises(runner.ReleaseManagerError, match="symlink"):
        runner.declared_autotask_read_profile(tmp_path)


def test_live_runtime_and_mcp_must_report_same_previous_profile(monkeypatch):
    calls = []
    def output(argv):
        calls.append(argv[2])
        return json.dumps(["OTHER=value", "JASON_PROVIDER_READ_ACTIVATION_PROFILE=" + V10])
    monkeypatch.setattr(runner, "output", output)
    assert runner.live_autotask_read_profile() == V10
    assert calls == ["jason-runtime", "jason-mcp-pilot"]


@pytest.mark.parametrize("profiles", [(V10, V11), ("unknown", V10), (V10, ""), (V11, V10)])
def test_inconsistent_unsupported_or_missing_runtime_profile_blocks(monkeypatch, profiles):
    def output(argv):
        name = argv[2]
        index = 0 if name == "jason-runtime" else 1
        value = profiles[index]
        return json.dumps(["JASON_PROVIDER_READ_ACTIVATION_PROFILE=" + value])
    monkeypatch.setattr(runner, "output", output)
    with pytest.raises(runner.ReleaseManagerError, match="Autotask.*(disagree|invalid)"):
        runner.live_autotask_read_profile()


def test_duplicate_profile_entries_fail_closed(monkeypatch):
    def output(argv):
        return json.dumps([
            "JASON_PROVIDER_READ_ACTIVATION_PROFILE=" + V10,
            "JASON_PROVIDER_READ_ACTIVATION_PROFILE=" + V11,
        ])
    monkeypatch.setattr(runner, "output", output)
    with pytest.raises(runner.ReleaseManagerError, match="invalid"):
        runner.live_autotask_read_profile()


def test_native_release_code_preserves_profile_during_rollback():
    source = (Path(__file__).resolve().parents[1] /
              "release_manager_host_runner.py").read_text()
    assert 'env["JASON_PROVIDER_READ_ACTIVATION_PROFILE"] = source_profile' in source
    assert 'env["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] = declared_rollback' in source
    assert 'env = deployment_env' in source
    assert 'native_deploy_environment(candidate_tree, image, mcp_image, candidate_sha)' in source
    assert 'rollback_env = autotask_rollback_environment(' in source
    assert 'result.pop("JASON_PROVIDER_READ_ACTIVATION_PROFILE", None)' in source
    assert 'result["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] = prior_autotask_profile' in source
    assert "post-deploy Autotask read activation profile mismatch" in source
    assert "invoking Autotask profile override conflicts with immutable candidate" in source


def test_immutable_pair_matches_actual_v10_restore(tmp_path):
    p=tmp_path / "config" / "autotask-entity-read-profile.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"schema_version":"1.0","read_profile":V11,"rollback_read_profile":V10}))
    assert runner.declared_autotask_read_profiles(tmp_path) == (V11,V10)


def test_native_rollback_profiles_must_not_pass_v10_as_candidate_override():
    """2026-10-27 real failure: passing v10 in candidate override refused both rollback scripts."""
    native_rollback_contract = runner.autotask_rollback_environment
    env = {
        "JASON_PROVIDER_READ_ACTIVATION_PROFILE": V11,
        "JASON_SOURCE_REVISION_OVERRIDE": "b" * 40,
        "JASON_RUNTIME_PRODUCTION_IMAGE": "jason-runtime:rollback-current",
        "JASON_MCP_PRODUCTION_IMAGE": "jason-mcp:rollback-current",
    }
    selected = native_rollback_contract(env, prior_autotask_profile=V10)
    assert "JASON_PROVIDER_READ_ACTIVATION_PROFILE" not in selected
    assert selected["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] == V10
    assert selected["JASON_SOURCE_REVISION_OVERRIDE"] == "b" * 40


def test_v13_dormant_profile_is_declared_for_future_exact_sha_native_review(tmp_path):
    from connectors.autotask.dynamic_schema_read import DYNAMIC_READ_PROFILE
    assert DYNAMIC_READ_PROFILE in runner.AUTOTASK_PROVIDER_READ_PROFILES
    declaration = tmp_path / "config" / "autotask-entity-read-profile.json"
    declaration.parent.mkdir()
    declaration.write_text(json.dumps({
        "schema_version":"1.0",
        "read_profile":DYNAMIC_READ_PROFILE,
        "rollback_read_profile":V11,
    }))
    assert runner.declared_autotask_read_profiles(tmp_path) == (
        DYNAMIC_READ_PROFILE,V11,
    )
    root=Path(__file__).resolve().parents[2]
    deployed=json.loads((root/"config/autotask-entity-read-profile.json").read_text())
    # The verified live rollback baseline ce52cc98 is already on v13.
    # The immutable source declaration must describe that actual LKG.
    assert deployed["read_profile"]==DYNAMIC_READ_PROFILE
    assert deployed["rollback_read_profile"]==DYNAMIC_READ_PROFILE
