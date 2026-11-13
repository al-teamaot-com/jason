import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "openclaw_workboard_release_scope.py"
spec = importlib.util.spec_from_file_location("workboard_scope", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixtures():
    original = {
        "agents": {"list": [{"id": "main"}]},
        "plugins": {"allow": ["msteams"], "entries": {"msteams": {"enabled": True}}},
        "gateway": {"mode": "local"},
    }
    base_bytes = (json.dumps(original, indent=2) + "\n").encode()
    candidate = mod.candidate_for(original)
    cand_bytes = (json.dumps(candidate, indent=2) + "\n").encode()
    manifest = {
        "candidate_id": "jman-workboard-activation-20261109",
        "base_config_sha256": mod.sha(base_bytes),
        "rollback_config_sha256": mod.sha(base_bytes),
        "candidate_config_sha256": mod.sha(cand_bytes),
        "reviewed_scope_sha256": "f" * 64,
    }
    return original, base_bytes, cand_bytes, manifest


def test_exact_scoped_activation_is_read_only_and_explicitly_non_authorizing():
    obj, base, cand, manifest = fixtures()
    before = json.dumps(obj)
    result = mod.verify(base, manifest, candidate_bytes=cand)
    assert json.dumps(obj) == before
    assert result["status"] == "preflight_passed"
    assert result["requires_authenticated_teams_release_approval"] is True
    assert result["production_authority_granted"] is False
    assert result["gateway_restart_authorized"] is False


@pytest.mark.parametrize("mutator", [
    lambda o: o["agents"]["list"].append({"id": "intruder"}),
    lambda o: o["plugins"]["entries"]["msteams"].update({"enabled": False}),
    lambda o: o["gateway"].update({"mode": "remote"}),
    lambda o: o["plugins"]["allow"].append("unreviewed-plugin"),
])
def test_unapproved_config_mutation_fails_closed(mutator):
    obj, base, cand, manifest = fixtures()
    value = json.loads(cand)
    mutator(value)
    with pytest.raises(mod.WorkboardScopeError):
        mod.verify(base, manifest, candidate_bytes=json.dumps(value).encode())


def test_baseline_drift_fails_before_approval():
    obj, base, cand, manifest = fixtures()
    with pytest.raises(mod.WorkboardScopeError, match="drift"):
        mod.verify(base + b" ", manifest, candidate_bytes=cand)


def test_candidate_byte_change_fails_even_when_semantically_equal():
    obj, base, cand, manifest = fixtures()
    with pytest.raises(mod.WorkboardScopeError, match="byte hash"):
        mod.verify(base, manifest, candidate_bytes=cand + b" ")


def test_unknown_scope_fails():
    obj, base, cand, manifest = fixtures()
    manifest["candidate_id"] = "unreviewed"
    with pytest.raises(mod.WorkboardScopeError, match="scope"):
        mod.verify(base, manifest, candidate_bytes=cand)


def test_missing_allowlist_fails():
    with pytest.raises(mod.WorkboardScopeError):
        mod.candidate_for({"plugins": {"entries": {}}})


def test_already_enabled_requires_fresh_review():
    obj, base, cand, manifest = fixtures()
    with pytest.raises(mod.WorkboardScopeError):
        mod.candidate_for(mod.candidate_for(obj))
