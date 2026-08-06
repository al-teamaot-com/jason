from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "retire_openbao_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("retire_openbao_bootstrap", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def protected(path: Path, value: str = "placeholder") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_check_only_performs_no_retirement(monkeypatch, capsys, tmp_path: Path) -> None:
    def denied(**kwargs):
        raise AssertionError("retire must not be called")

    monkeypatch.setattr(MODULE, "retire", denied)
    result = MODULE.main(["--check-only", "--evidence-output", str(tmp_path / "evidence.json")])
    assert result == 0
    assert "no token read" in capsys.readouterr().out
    assert not (tmp_path / "evidence.json").exists()


def test_private_file_rejects_broad_permissions(tmp_path: Path) -> None:
    path = protected(tmp_path / "token")
    path.chmod(0o640)
    try:
        MODULE.ensure_private_file(path)
    except PermissionError:
        pass
    else:
        raise AssertionError("Broad permissions were not rejected.")


def test_retirement_validates_runtime_before_revocation(monkeypatch, tmp_path: Path) -> None:
    bootstrap = protected(tmp_path / "bootstrap.token")
    contract = protected(tmp_path / "contract.value")
    runtime = protected(tmp_path / "runtime.token")
    wrapper = protected(tmp_path / "jason-secret")
    wrapper.chmod(0o700)
    calls: list[str] = []

    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 0)

    def fail_validation(**kwargs):
        calls.append("validate")
        raise RuntimeError("runtime unhealthy")

    def revoke(*args, **kwargs):
        calls.append("revoke")

    monkeypatch.setattr(MODULE, "run_wrapper_validation", fail_validation)
    monkeypatch.setattr(MODULE, "revoke_self", revoke)

    try:
        MODULE.retire(
            address="http://127.0.0.1:8200",
            bootstrap_token_file=bootstrap,
            contract_value_file=contract,
            runtime_token_file=runtime,
            wrapper=wrapper,
            evidence_output=tmp_path / "evidence.json",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Unhealthy runtime was not rejected.")

    assert calls == ["validate"]
    assert bootstrap.exists()
    assert contract.exists()


def test_successful_retirement_removes_inputs_and_writes_safe_evidence(monkeypatch, tmp_path: Path) -> None:
    bootstrap = protected(tmp_path / "bootstrap.token")
    contract = protected(tmp_path / "contract.value")
    runtime = protected(tmp_path / "runtime.token")
    wrapper = protected(tmp_path / "jason-secret")
    wrapper.chmod(0o700)
    output = tmp_path / "evidence" / "retirement.json"
    revoked: list[str] = []

    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 0)
    monkeypatch.setattr(MODULE, "run_wrapper_validation", lambda **kwargs: None)
    monkeypatch.setattr(MODULE, "revoke_self", lambda address, token: revoked.append(token))

    evidence = MODULE.retire(
        address="http://127.0.0.1:8200",
        bootstrap_token_file=bootstrap,
        contract_value_file=contract,
        runtime_token_file=runtime,
        wrapper=wrapper,
        evidence_output=output,
    )

    assert revoked == ["placeholder"]
    assert not bootstrap.exists()
    assert not contract.exists()
    assert output.exists()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == evidence
    assert stored["bootstrap_token_revoked"] is True
    assert stored["bootstrap_token_file_removed"] is True
    assert stored["contract_value_file_removed"] is True
    assert stored["protected_values_exposed"] is False
    serialized = output.read_text(encoding="utf-8")
    assert "placeholder" not in serialized
    assert "client_token" not in serialized


def test_existing_evidence_blocks_before_runtime_or_revocation(monkeypatch, tmp_path: Path) -> None:
    bootstrap = protected(tmp_path / "bootstrap.token")
    contract = protected(tmp_path / "contract.value")
    runtime = protected(tmp_path / "runtime.token")
    wrapper = protected(tmp_path / "jason-secret")
    wrapper.chmod(0o700)
    output = protected(tmp_path / "evidence.json", "existing")
    calls: list[str] = []

    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 0)
    monkeypatch.setattr(MODULE, "run_wrapper_validation", lambda **kwargs: calls.append("validate"))
    monkeypatch.setattr(MODULE, "revoke_self", lambda *args, **kwargs: calls.append("revoke"))

    try:
        MODULE.retire(
            address="http://127.0.0.1:8200",
            bootstrap_token_file=bootstrap,
            contract_value_file=contract,
            runtime_token_file=runtime,
            wrapper=wrapper,
            evidence_output=output,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing evidence was not rejected.")

    assert calls == []
    assert bootstrap.exists()
    assert contract.exists()
