from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "openbao_recovery_fingerprint.py"
SPEC = importlib.util.spec_from_file_location("openbao_recovery_fingerprint", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_init(path: Path, *, mode: int = 0o600) -> None:
    path.write_text(
        json.dumps(
            {
                "unseal_keys_b64": ["one", "two", "three", "four", "five"],
                "unseal_shares": 5,
                "unseal_threshold": 3,
                "root_token": None,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(mode)


def test_initialization_metadata_contains_no_protected_values(tmp_path: Path) -> None:
    init_file = tmp_path / "init.json"
    write_init(init_file)

    result = MODULE._load_initialization_metadata(init_file)

    assert result["share_count"] == 5
    assert result["threshold"] == 3
    assert result["root_token_present"] is False
    assert result["protected_values_exposed"] is False
    serialized = json.dumps(result)
    for protected in ("one", "two", "three", "four", "five"):
        assert protected not in serialized


def test_broad_permissions_are_denied(tmp_path: Path) -> None:
    init_file = tmp_path / "init.json"
    write_init(init_file, mode=0o640)

    with pytest.raises(MODULE.FingerprintError, match="permissions are too broad"):
        MODULE._load_initialization_metadata(init_file)


def test_share_count_mismatch_is_denied(tmp_path: Path) -> None:
    init_file = tmp_path / "init.json"
    init_file.write_text(
        json.dumps(
            {
                "unseal_keys_b64": ["one", "two", "three"],
                "unseal_shares": 5,
                "unseal_threshold": 3,
            }
        ),
        encoding="utf-8",
    )
    init_file.chmod(0o600)

    with pytest.raises(MODULE.FingerprintError, match="share count"):
        MODULE._load_initialization_metadata(init_file)


def test_existing_output_is_denied(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("existing\n", encoding="utf-8")

    with pytest.raises(MODULE.FingerprintError, match="already exists"):
        MODULE._require_new_output(output)


def test_check_only_writes_no_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "evidence.json"
    result = MODULE.main(["--output", str(output), "--check-only"])

    assert result == 0
    assert not output.exists()
    assert "no protected file read" in capsys.readouterr().out
