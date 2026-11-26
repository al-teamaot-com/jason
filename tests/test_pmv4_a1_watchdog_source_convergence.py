"""One optional A1 shadow container in desired state; zero guard weakening."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from tools import production_drift_guard as guard


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "33044085e1df5ad430ec7f29492801ac7219d4a8"
NAME = "jason-pmv4-shadow-gateway"


def baseline():
    blob = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         BASE_SHA + ":config/production-desired-state.json"],
        capture_output=True, check=True, timeout=10,
    ).stdout
    return json.loads(blob)


def candidate():
    return json.loads(
        (ROOT / "config/production-desired-state.json").read_text())


def test_exact_one_optional_allowance_no_other_change():
    before = baseline()
    after = candidate()
    assert before["schema_version"] == after["schema_version"] == "1.0"
    assert set(before) == set(after)
    assert NAME not in before["allowed_running_containers"]
    assert NAME not in before["required_containers"]
    assert after["allowed_running_containers"] == (
        before["allowed_running_containers"] + [NAME])
    assert all(
        after[field] == before[field]
        for field in before if field != "allowed_running_containers")
    assert NAME not in after["required_containers"]
    assert len(after["allowed_running_containers"]) == len(
        set(after["allowed_running_containers"]))


def evaluate(policy, running):
    with (
        patch.object(guard, "unit_names",
                     side_effect=[set(), set()]),
        patch.object(guard, "active_state", return_value="active"),
        patch.object(guard, "unit_properties",
                     return_value={"WorkingDirectory": "/opt/jason/current",
                                   "ExecStart": "/opt/jason/current/start"}),
        patch.object(guard, "running_containers",
                     return_value=set(running)),
        patch.object(guard, "stopped_rollback_containers",
                     return_value=[]),
    ):
        # Suppress unrelated existing systemd-required notices only for these
        # focused container-allowlist assertions, not in source policy.
        p = deepcopy(policy)
        p["required_system_units"] = []
        p["required_user_units"] = []
        p["allowed_system_units"] = []
        p["allowed_user_units"] = []
        return guard.evaluate(p)


def test_shadow_can_be_absent_or_present_without_becoming_required():
    before = baseline()
    after = candidate()
    required = set(before["required_containers"])
    absent = evaluate(after, required)
    assert absent["status"] == "pass"
    present = evaluate(after, required | {NAME})
    assert present["status"] == "pass"
    assert present["problems"] == []


def test_unrelated_container_still_triggers_drift():
    after = candidate()
    observed = set(after["required_containers"]) | {NAME, "unreviewed-provider"}
    report = evaluate(after, observed)
    assert report["status"] == "drift_detected"
    assert any(
        x.get("kind") == "undeclared_running_container"
        and x.get("container") == "unreviewed-provider"
        for x in report["problems"])


def test_before_policy_correctly_rejects_shadow():
    before = baseline()
    observed = set(before["required_containers"]) | {NAME}
    report = evaluate(before, observed)
    assert report["status"] == "drift_detected"
    assert any(
        x.get("kind") == "undeclared_running_container"
        and x.get("container") == NAME
        for x in report["problems"])
