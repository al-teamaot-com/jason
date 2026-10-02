from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bootstrap.candidate_dependencies import (
    build_candidate_dependency_plan,
    load_candidate_dependency_config,
    prepare_candidate_dependencies,
    verify_candidate_dependencies,
)
from bootstrap.candidate_host import CandidateHostIdentity


ROOT = Path(__file__).resolve().parents[2]


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def config():
    return load_candidate_dependency_config(
        ROOT / "config/candidate-dependencies.v1.json",
        ROOT / "config/schemas/candidate-dependencies.schema.json",
    )


def candidate_root(tmp_path: Path):
    root = tmp_path / "candidate"
    openbao = (
        root
        / "opt/jason/current/deploy/openbao/config/openbao.hcl"
    )
    openbao.parent.mkdir(parents=True, exist_ok=True)
    openbao.write_text('storage "raft" { path = "/openbao/data" }\n')
    return root


class StateRunner:
    def __init__(self):
        self.networks = set()
        self.containers = {}
        self.models = set()
        self.calls = []

    def __call__(self, command):
        command = tuple(command)
        self.calls.append(command)
        if command[:3] == ("docker", "network", "inspect"):
            return SimpleNamespace(
                returncode=0 if command[-1] in self.networks else 1,
                stdout="",
                stderr="",
            )
        if command[:3] == ("docker", "network", "create"):
            self.networks.add(command[-1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ("docker", "inspect", "--format"):
            name = command[-1]
            state = self.containers.get(name)
            if state is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            return SimpleNamespace(
                returncode=0,
                stdout=state + "\n",
                stderr="",
            )
        if command[:3] == ("docker", "compose", "--project-name"):
            self.containers["openbao"] = "running"
            self.containers["jason-ollama"] = "healthy"
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command == (
            "docker",
            "exec",
            "openbao",
            "bao",
            "status",
            "-format=json",
        ):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {"initialized": True, "sealed": False}
                ),
                stderr="",
            )
        if command == (
            "docker",
            "exec",
            "jason-ollama",
            "ollama",
            "list",
        ):
            rows = ["NAME ID SIZE"]
            rows.extend(
                model + " abc 1GB"
                for model in sorted(self.models)
            )
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(rows) + "\n",
                stderr="",
            )
        if command[:5] == (
            "docker",
            "exec",
            "jason-ollama",
            "ollama",
            "pull",
        ):
            self.models.add(command[5])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)


def test_dependency_plan_uses_canonical_state_outside_immutable_release(
    tmp_path,
):
    root = candidate_root(tmp_path)
    plan = build_candidate_dependency_plan(
        target_root=root,
        candidate_identity=identity(),
        dependency_config=config(),
        ollama_model="qwen-test",
    )
    assert plan.status == "ready_for_dependency_prepare"
    text = Path(plan.compose_file).read_text()
    assert str(root / "var/lib/jason/openbao/data") in text
    assert str(root / "var/lib/jason/cache/ollama") in text
    assert str(root / "opt/jason/current/deploy/openbao/config") in text
    assert "/deploy/openbao/data" not in text


def test_prepare_creates_networks_and_dependency_state(tmp_path):
    runner = StateRunner()
    root = candidate_root(tmp_path)
    plan = build_candidate_dependency_plan(
        target_root=root,
        candidate_identity=identity(),
        dependency_config=config(),
        ollama_model="qwen-test",
    )
    result = prepare_candidate_dependencies(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
    )
    assert result["status"] == "dependency_services_started"
    assert runner.networks == {
        "jason-core",
        "jason-observability",
        "openclaw_default",
    }
    assert (root / "var/lib/jason/openbao/data").is_dir()
    assert (root / "var/lib/jason/cache/ollama").is_dir()


def test_dependency_verify_requires_unsealed_openbao_and_model(tmp_path):
    runner = StateRunner()
    runner.networks.update(
        {"jason-core", "jason-observability", "openclaw_default"}
    )
    runner.containers.update(
        {"openbao": "running", "jason-ollama": "healthy"}
    )
    root = candidate_root(tmp_path)
    plan = build_candidate_dependency_plan(
        target_root=root,
        candidate_identity=identity(),
        dependency_config=config(),
        ollama_model="qwen-test",
    )
    blocked = verify_candidate_dependencies(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
    )
    assert blocked["status"] == "blocked"
    assert "ollama_model_unavailable:qwen-test" in blocked["blockers"]

    ready = verify_candidate_dependencies(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
        pull_ollama_model=True,
    )
    assert ready["status"] == "ready"
    assert "qwen-test" in runner.models


def test_sealed_openbao_blocks_dependency_readiness(tmp_path):
    runner = StateRunner()
    runner.networks.update(
        {"jason-core", "jason-observability", "openclaw_default"}
    )
    runner.containers.update(
        {"openbao": "running", "jason-ollama": "healthy"}
    )
    runner.models.add("qwen-test")
    root = candidate_root(tmp_path)
    plan = build_candidate_dependency_plan(
        target_root=root,
        candidate_identity=identity(),
        dependency_config=config(),
        ollama_model="qwen-test",
    )

    original = runner.__call__

    def sealed(command):
        if tuple(command) == (
            "docker",
            "exec",
            "openbao",
            "bao",
            "status",
            "-format=json",
        ):
            return SimpleNamespace(
                returncode=2,
                stdout=json.dumps(
                    {"initialized": True, "sealed": True}
                ),
                stderr="",
            )
        return original(command)

    result = verify_candidate_dependencies(
        plan=plan,
        candidate_identity=identity(),
        runner=sealed,
    )
    assert result["status"] == "blocked"
    assert "openbao_not_ready:sealed" in result["blockers"]
