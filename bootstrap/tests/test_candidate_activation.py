from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bootstrap.candidate_activation import (
    CandidateActivationError,
    CandidateHostIdentity,
    build_candidate_activation_plan,
    execute_candidate_activation_plan,
    load_candidate_host_identity,
)
from bootstrap.install_runtime import (
    load_resources,
)


ROOT = Path(__file__).resolve().parents[2]


def resources():
    return load_resources(
        ROOT / "config/bootstrap-resources.v1.json",
        ROOT / "config/schemas/bootstrap-resources.schema.json",
    )


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def prepared_root(tmp_path: Path):
    root = tmp_path / "candidate"
    (root / "opt/jason/releases/a").mkdir(parents=True)
    (root / "opt/jason/releases/a/tools").mkdir(parents=True)
    (root / "opt/jason/releases/a/tools/delegation_maintenance.py").write_text("x")
    (root / "opt/jason/releases/a/tools/openclaw_authority_health_snapshot.py").write_text("x")
    (root / "opt/jason").mkdir(parents=True, exist_ok=True)
    (root / "opt/jason/current").symlink_to("releases/a")

    (root / "var/lib/jason").mkdir(parents=True)
    (root / "var/lib/jason/bootstrap-runtime.json").write_text("{}")

    for path in (
        "var/lib/jason/authority/authority.sqlite3",
        "var/lib/jason/authority/client-boundaries.sqlite3",
        "var/lib/jason/openclaw/orchestration-events.sqlite3",
        "var/lib/jason/openclaw/approval-continuations.sqlite3",
    ):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"x")

    units = root / "etc/systemd/system"
    units.mkdir(parents=True)
    for unit in resources()["systemd_units"]:
        if not unit["portable"]:
            continue
        source = ROOT / unit["source"]
        (units / source.name).write_text(source.read_text())
    return root


def test_candidate_host_identity_fails_closed_for_production(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "production",
                "instance_id": "prod",
                "bootstrap_authorized": True,
            }
        )
    )
    with pytest.raises(CandidateActivationError, match="not candidate"):
        load_candidate_host_identity(path)


def test_activation_plan_contains_only_required_networks_and_portable_units(tmp_path):
    root = prepared_root(tmp_path)
    plan = build_candidate_activation_plan(
        target_root=root,
        resources=resources(),
        candidate_identity=identity(),
    )
    networks = [
        action.arguments[0]
        for action in plan.actions
        if action.action == "ensure_docker_network"
    ]
    units = [
        action.arguments[0]
        for action in plan.actions
        if action.action == "enable_systemd_unit"
    ]
    assert networks == ["jason-core", "jason-observability"]
    assert "jason-delegation-maintenance.service" in units
    assert "jason-kfs-collector.service" not in units


def test_executor_refuses_non_root_target_even_for_candidate(tmp_path):
    root = prepared_root(tmp_path)
    plan = build_candidate_activation_plan(
        target_root=root,
        resources=resources(),
        candidate_identity=identity(),
    )
    with pytest.raises(CandidateActivationError, match="candidate host root"):
        execute_candidate_activation_plan(plan=plan, runner=lambda command: None)


def test_executor_creates_missing_networks_and_enables_units_without_starting_services():
    plan = build_candidate_activation_plan
    actions = (
        ("docker", "network", "inspect", "jason-core"),
        ("docker", "network", "create", "jason-core"),
        ("docker", "network", "inspect", "jason-observability"),
        ("systemctl", "enable", "jason-delegation-maintenance.service"),
    )
    calls = []

    def runner(command):
        calls.append(tuple(command))
        if tuple(command) == actions[0]:
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    from bootstrap.candidate_activation import CandidateActivationPlan, ActivationAction

    candidate_plan = CandidateActivationPlan(
        schema_version="1.0",
        instance_id="jason-b",
        target_root="/",
        actions=(
            ActivationAction("ensure_docker_network", ("jason-core",), True),
            ActivationAction("ensure_docker_network", ("jason-observability",), True),
            ActivationAction("enable_systemd_unit", ("jason-delegation-maintenance.service",), True),
        ),
    )
    result = execute_candidate_activation_plan(
        plan=candidate_plan,
        runner=runner,
    )
    assert result["services_started"] is False
    assert result["provider_secrets_enrolled"] is False
    assert ("docker", "network", "create", "jason-core") in calls
    assert ("systemctl", "start", "jason-delegation-maintenance.service") not in calls
