from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "openbao_deployment_verification.py"
SPEC = importlib.util.spec_from_file_location("openbao_deployment_verification", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_redacts_sensitive_lines() -> None:
    text = "safe=value\nroot_token=do-not-show\npassword=hidden"

    redacted = MODULE._redact(text)

    assert "safe=value" in redacted
    assert "do-not-show" not in redacted
    assert "hidden" not in redacted
    assert redacted.count("[REDACTED SENSITIVE LINE]") == 2


def test_timeout_returns_bounded_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: f"/usr/bin/{name}")

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    result = MODULE._run(("systemctl", "show", "openbao.service"), runner=runner, timeout_seconds=1.0)

    assert result.status == "timeout"
    assert "openbao.service" in result.name


def test_file_probe_records_hash_without_contents(tmp_path: Path) -> None:
    target = tmp_path / "unit.service"
    target.write_text("ExecStart=/safe/path\n", encoding="utf-8")

    result = MODULE._file_probe(target)

    assert result.status == "ok"
    assert "sha256=" in result.value
    assert "ExecStart" not in result.value


def test_output_must_be_outside_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.chdir(repository)

    with pytest.raises(PermissionError, match="outside the repository"):
        MODULE._validate_output(repository / "evidence.json")


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="overwrite"):
        MODULE._validate_output(output)


def test_markdown_identifies_evidence_as_non_approval() -> None:
    report = MODULE.VerificationReport(
        schema_version="0.1",
        collected_at="2026-08-05T00:00:00+00:00",
        host="jason",
        probes=(MODULE.ProbeResult("probe", "ok", "value", "source"),),
        overall_status="evidence_collected",
    )

    rendered = MODULE.render_markdown(report)

    assert "not itself an approval" in rendered
    assert "| `probe` | `ok` | value | `source` |" in rendered
