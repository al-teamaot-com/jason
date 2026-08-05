from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import sys


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "provision_openbao_contract_test.py"
SPEC = importlib.util.spec_from_file_location("provision_openbao_contract_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_policy_is_read_only_and_scoped() -> None:
    assert 'path "secret/data/jason/contract-test"' in MODULE.POLICY_TEXT
    assert 'capabilities = ["read"]' in MODULE.POLICY_TEXT
    assert "create" not in MODULE.POLICY_TEXT
    assert "update" not in MODULE.POLICY_TEXT
    assert "delete" not in MODULE.POLICY_TEXT


def test_private_file_rejects_group_or_other_permissions(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("placeholder\n", encoding="utf-8")
    path.chmod(0o640)
    try:
        MODULE.ensure_private_file(path)
    except PermissionError:
        pass
    else:
        raise AssertionError("Broad permissions were not rejected.")


def test_private_file_accepts_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("placeholder\n", encoding="utf-8")
    path.chmod(0o600)
    MODULE.ensure_private_file(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_check_only_makes_no_provisioning_call(monkeypatch, capsys) -> None:
    def denied(**kwargs):
        raise AssertionError("provision must not be called")

    monkeypatch.setattr(MODULE, "provision", denied)
    result = MODULE.main(["--check-only"])
    assert result == 0
    output = capsys.readouterr().out
    assert "no OpenBao request made" in output


def test_evidence_schema_contains_no_secret_value() -> None:
    expected = {
        "address",
        "policy",
        "contract_path",
        "token_path",
        "token_mode",
        "health",
        "contract_test",
        "secret_value_exposed",
    }
    assert "client_token" not in expected
    assert "contract_value" not in expected
