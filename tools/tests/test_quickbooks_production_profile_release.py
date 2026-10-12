from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "release_manager_host_runner.py"
GATE = ROOT / "tools" / "release_manager_gate.py"


def load_runner():
    if "release_manager_gate" not in sys.modules:
        gate_spec = importlib.util.spec_from_file_location("release_manager_gate", GATE)
        gate = importlib.util.module_from_spec(gate_spec)
        sys.modules["release_manager_gate"] = gate
        assert gate_spec.loader is not None
        gate_spec.loader.exec_module(gate)
    spec = importlib.util.spec_from_file_location("jason_quickbooks_release_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_candidate_source_declares_production_read_profile():
    runner = load_runner()
    assert runner.declared_quickbooks_read_profile(ROOT) == "quickbooks-production-read-v1"


def test_declared_profile_rejects_unknown_or_extra_fields(tmp_path):
    runner = load_runner()
    config = tmp_path / "config"
    config.mkdir()
    (config / "quickbooks-read-profile.json").write_text(
        json.dumps({"schema_version": "1.0", "read_profile": "unsafe-write-profile"})
    )
    with pytest.raises(runner.ReleaseManagerError, match="declaration invalid"):
        runner.declared_quickbooks_read_profile(tmp_path)
    (config / "quickbooks-read-profile.json").write_text(
        json.dumps({"schema_version": "1.0",
                    "read_profile": "quickbooks-production-read-v1",
                    "write_enabled": True})
    )
    with pytest.raises(runner.ReleaseManagerError, match="declaration invalid"):
        runner.declared_quickbooks_read_profile(tmp_path)


def test_live_profile_must_match_on_runtime_and_mcp():
    runner = load_runner()
    sandbox = json.dumps(["JASON_QUICKBOOKS_READ_PROFILE=quickbooks-sandbox-read-v1"])
    production = json.dumps(["JASON_QUICKBOOKS_READ_PROFILE=quickbooks-production-read-v1"])
    with patch.object(runner, "output", side_effect=[sandbox, sandbox]):
        assert runner.live_quickbooks_read_profile() == "quickbooks-sandbox-read-v1"
    with patch.object(runner, "output", side_effect=[sandbox, production]):
        with pytest.raises(runner.ReleaseManagerError, match="disagree"):
            runner.live_quickbooks_read_profile()


def test_rollback_restores_sandbox_when_candidate_selected_production():
    runner = load_runner()
    original = {
        "JASON_QUICKBOOKS_READ_PROFILE": "quickbooks-production-read-v1",
        "JASON_RUNTIME_PRODUCTION_IMAGE": "jason-runtime:release-new",
        "JASON_MCP_PRODUCTION_IMAGE": "jason-mcp:release-new",
        "JASON_SOURCE_REVISION_OVERRIDE": "b" * 40,
        "UNRELATED_SETTING": "preserved",
    }
    out = runner.quickbooks_rollback_environment(
        original, rollback_sha="a" * 40, prior_profile="quickbooks-sandbox-read-v1"
    )
    assert out["JASON_QUICKBOOKS_READ_PROFILE"] == "quickbooks-sandbox-read-v1"
    assert out["JASON_RUNTIME_PRODUCTION_IMAGE"] == "jason-runtime:rollback-current"
    assert out["JASON_MCP_PRODUCTION_IMAGE"] == "jason-mcp:rollback-current"
    assert out["JASON_SOURCE_REVISION_OVERRIDE"] == "a" * 40
    assert out["UNRELATED_SETTING"] == "preserved"
    assert original["JASON_QUICKBOOKS_READ_PROFILE"] == "quickbooks-production-read-v1"


def test_unknown_rollback_profile_fails_closed():
    runner = load_runner()
    with pytest.raises(runner.ReleaseManagerError, match="not supported"):
        runner.quickbooks_rollback_environment(
            {}, rollback_sha="a" * 40, prior_profile="quickbooks-unapproved-write-v1"
        )


def test_legacy_candidate_without_profile_declaration_preserves_live_selection(tmp_path):
    runner = load_runner()
    assert runner.declared_quickbooks_read_profile(tmp_path) is None
