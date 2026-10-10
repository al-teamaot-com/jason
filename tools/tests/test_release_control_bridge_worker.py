import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
import pytest

PATH = Path(__file__).resolve().parents[1] / "release_control_bridge_worker.py"
spec = importlib.util.spec_from_file_location("release_control_bridge_worker", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_root_only(tmp_path):
    with patch.object(mod.os, "geteuid", return_value=1000):
        with pytest.raises(PermissionError, match="root-only"):
            mod.publish()


def test_protected_readback_keeps_original_unchanged(tmp_path):
    root = tmp_path
    for name in ("production-control-state.json", "production-drift.json"):
        path = root / name
        path.write_text(json.dumps({"schema_version": "1.0", "status": "pass"}))
        path.chmod(0o600)
    with patch.object(mod, "ROOT", root), patch.object(mod, "STATE", root / "production-control-state.json"), patch.object(mod, "DRIFT", root / "production-drift.json"), patch.object(mod, "SNAPSHOT", root / "protected-readback"), patch.object(mod, "pwd") as pwd, patch.object(mod.os, "geteuid", return_value=0), patch.object(mod.os, "chown"):
        pwd.getpwnam.return_value = SimpleNamespace(pw_uid=root.stat().st_uid, pw_gid=root.stat().st_gid)
        real_fstat = os.fstat
        with patch.object(mod.os, "fstat", side_effect=lambda fd: SimpleNamespace(st_mode=real_fstat(fd).st_mode, st_uid=0)):
            mod.publish()
    for name in ("production-control-state.json", "production-drift.json"):
        assert json.loads((root / "protected-readback" / name).read_text())["status"] == "pass"
        assert (root / name).stat().st_mode & 0o777 == 0o600
