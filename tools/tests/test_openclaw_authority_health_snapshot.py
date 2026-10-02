from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "openclaw_authority_health_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("openclaw_authority_health_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_snapshot_uses_bounded_timeout_for_full_integrity_checks(monkeypatch, tmp_path):
    module = _load_module()
    observed = {}

    class Completed:
        stdout = json.dumps({"status": "pass"})
        returncode = 0

    def fake_run(*args, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(tmp_path / "health.json")])

    assert module.main() == 0
    assert observed["timeout"] == 120
    assert json.loads((tmp_path / "health.json").read_text())["status"] == "pass"
