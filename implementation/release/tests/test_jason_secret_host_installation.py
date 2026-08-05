from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "deploy_jason_secret_host.py"
SPEC = importlib.util.spec_from_file_location("deploy_jason_secret_host_installation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_non_secret_install_does_not_require_token(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "jason_secret.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    library = tmp_path / "opt" / "jason_secret.py"
    launcher = tmp_path / "bin" / "jason-secret"
    mapping = tmp_path / "etc" / "secret-mappings.json"
    token = tmp_path / "etc" / "openbao.token"

    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 0)

    evidence = MODULE.install_non_secret_components(
        source=source,
        library_path=library,
        launcher_path=launcher,
        mapping_path=mapping,
        token_path=token,
    )

    assert evidence["phase"] == "non_secret_components_installed"
    assert evidence["token_present"] is False
    assert evidence["openbao_contacted"] is False
    assert evidence["secret_resolved"] is False
    assert library.is_file()
    assert launcher.is_file()
    assert mapping.is_file()
    assert json.loads(mapping.read_text(encoding="utf-8"))["jason.contract-test"]["field"] == "value"


def test_non_secret_install_requires_root(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "jason_secret.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr(MODULE.os, "geteuid", lambda: 1000)

    try:
        MODULE.install_non_secret_components(
            source=source,
            library_path=tmp_path / "library.py",
            launcher_path=tmp_path / "launcher",
            mapping_path=tmp_path / "mapping.json",
            token_path=tmp_path / "token",
        )
    except PermissionError as exc:
        assert "root" in str(exc)
    else:
        raise AssertionError("non-root installation was incorrectly approved")


def test_evidence_writer_denies_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("existing\n", encoding="utf-8")

    try:
        MODULE.write_evidence(output, {"status": "approved"})
    except FileExistsError:
        pass
    else:
        raise AssertionError("evidence overwrite was incorrectly approved")
