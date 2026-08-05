from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "deploy_jason_secret_host.py"
SPEC = importlib.util.spec_from_file_location("deploy_jason_secret_host", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_check_only_validates_source_without_changes(tmp_path, capsys):
    source = tmp_path / "jason_secret.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    result = MODULE.main(["--source", str(source), "--check-only"])
    assert result == 0
    assert "no files changed" in capsys.readouterr().out


def test_private_file_rejects_group_or_world_permissions(tmp_path):
    token = tmp_path / "token"
    token.write_text("placeholder", encoding="utf-8")
    token.chmod(0o644)
    try:
        MODULE.ensure_private_file(token)
    except PermissionError:
        pass
    else:
        raise AssertionError("Broad token permissions were incorrectly accepted")


def test_default_mapping_contains_only_logical_contract_reference():
    assert MODULE.DEFAULT_MAPPINGS == {
        "jason.contract-test": {
            "path": "secret/data/jason/contract-test",
            "field": "value",
        }
    }
    assert "token" not in json.dumps(MODULE.DEFAULT_MAPPINGS).lower()
