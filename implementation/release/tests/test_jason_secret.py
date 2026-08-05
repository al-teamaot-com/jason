from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "jason_secret.py"
SPEC = importlib.util.spec_from_file_location("jason_secret", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _files(tmp_path: Path) -> tuple[Path, Path]:
    mappings = tmp_path / "mappings.json"
    values = tmp_path / "values.json"
    mappings.write_text(
        json.dumps({"example.value": {"path": "secret/data/example", "field": "value"}}),
        encoding="utf-8",
    )
    values.write_text(
        json.dumps({"secret/data/example": {"value": "top-secret-value"}}),
        encoding="utf-8",
    )
    return mappings, values


def test_resolve_prints_only_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mappings, values = _files(tmp_path)
    result = MODULE.run(
        ["example.value", "--mapping-file", str(mappings)],
        environment={
            "JASON_SECRET_BACKEND": "test-file",
            "JASON_SECRET_TEST_VALUES_FILE": str(values),
        },
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "top-secret-value\n"
    assert captured.err == ""


def test_contract_test_never_prints_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mappings, values = _files(tmp_path)
    result = MODULE.run(
        ["--contract-test", "example.value", "--mapping-file", str(mappings)],
        environment={
            "JASON_SECRET_BACKEND": "test-file",
            "JASON_SECRET_TEST_VALUES_FILE": str(values),
        },
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "contract-ok\n"
    assert "top-secret-value" not in captured.out + captured.err


def test_health_does_not_resolve_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, values = _files(tmp_path)
    result = MODULE.run(
        ["--health"],
        environment={
            "JASON_SECRET_BACKEND": "test-file",
            "JASON_SECRET_TEST_VALUES_FILE": str(values),
        },
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "healthy\n"
    assert "top-secret-value" not in captured.out + captured.err


def test_unknown_mapping_returns_not_found_without_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mappings, values = _files(tmp_path)
    result = MODULE.run(
        ["missing.value", "--mapping-file", str(mappings)],
        environment={
            "JASON_SECRET_BACKEND": "test-file",
            "JASON_SECRET_TEST_VALUES_FILE": str(values),
        },
    )
    captured = capsys.readouterr()
    assert result == MODULE.EXIT_NOT_FOUND
    assert captured.out == ""
    assert "top-secret-value" not in captured.err


def test_openbao_requires_external_auth_configuration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mappings, _ = _files(tmp_path)
    result = MODULE.run(
        ["example.value", "--mapping-file", str(mappings)],
        environment={"JASON_SECRET_BACKEND": "openbao"},
    )
    captured = capsys.readouterr()
    assert result == MODULE.EXIT_UNAUTHORIZED
    assert captured.out == ""
    assert "not configured" in captured.err
