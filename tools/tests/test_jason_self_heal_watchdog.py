from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "jason_self_heal_watchdog",
    ROOT / "tools" / "jason_self_heal_watchdog.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_fingerprint_is_order_independent():
    assert module.fingerprint(["b", "a"]) == module.fingerprint(["a", "b"])


def test_bounded_recovery_restarts_only_failed_local_surface(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "container_running", lambda name: True)

    actions = module.bounded_recovery(["mcp_status_functional_failure"])

    assert calls == [["docker", "restart", "-t", "10", "jason-mcp-pilot"]]
    assert "docker restart jason-mcp-pilot" in actions[0]


def test_queue_support_repair_persists_stable_auto_support_item(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    path = module.queue_support_repair(
        tmp_path,
        "abcdef1234567890",
        ["provider_canary_failure"],
        {"sample": True},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["support_item"] == "SUPPORT-AUTO-ABCDEF123456"
    assert payload["state"] == "repair_required"
    assert calls[-1][:4] == ["systemctl", "--user", "start", "jason-support-repair-worker.service"]


def test_escalation_payload_requires_owner_action(tmp_path):
    path = module.write_escalation(
        tmp_path,
        fp="abc123",
        failures=["mcp_status_functional_failure"],
        attempts=2,
        actions=["docker restart jason-mcp-pilot: rc=0"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["state"] == "owner_action_required"
    assert payload["attempts"] == 2
    assert "Owner action" not in payload["owner_action"]
    assert payload["owner_action"]
