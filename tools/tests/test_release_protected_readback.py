import importlib.util
import json
import os
import time
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "release_manager_host_runner.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("release_manager_host_runner_readback", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_protected_readback_fails_closed_when_missing_or_stale(tmp_path):
    with pytest.raises(mod.ReleaseManagerError, match="unavailable"):
        mod._read_protected_snapshot(tmp_path, "production-control-state.json")
    directory = tmp_path / "protected-readback"
    directory.mkdir()
    snapshot = directory / "production-control-state.json"
    snapshot.write_text(json.dumps({"schema_version": "1.0", "circuit_breaker": {"state": "open"}}))
    os.utime(snapshot, (time.time() - 180, time.time() - 180))
    with pytest.raises(mod.ReleaseManagerError, match="stale"):
        mod._read_protected_snapshot(tmp_path, "production-control-state.json")
    os.utime(snapshot, None)
    assert mod._read_protected_snapshot(tmp_path, "production-control-state.json")["circuit_breaker"]["state"] == "open"


def test_protected_snapshot_does_not_grant_circuit_breaker_write(tmp_path):
    directory = tmp_path / "protected-readback"
    directory.mkdir()
    snapshot = directory / "production-control-state.json"
    snapshot.write_text(json.dumps({"schema_version": "1.0", "circuit_breaker": {"state": "open"}}))
    with patch.object(mod, "atomic_json", side_effect=PermissionError("root boundary")):
        with pytest.raises(PermissionError):
            mod.save_control_state(tmp_path, {"circuit_breaker": {"state": "closed"}})
    assert json.loads(snapshot.read_text())["circuit_breaker"]["state"] == "open"
