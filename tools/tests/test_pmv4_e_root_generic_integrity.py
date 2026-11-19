"""Root controller preflight: byte-exact unchanged guard plus reason evidence."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import stat
from hashlib import sha256

import pytest

from tools import pmv4_e_canary_oneowner_root as root


def fixture(tmp_path,monkeypatch,*,change=None):
    baselines=(
        ("tools/independent_component_release.py","CONTROLLER_SHA"),
        ("tools/independent_component_host_adapter.py","ADAPTER_SHA"),
        ("tools/independent_component_release_root.py","ROOT_ENTRY_SHA"),
    )
    for i,(relative,key) in enumerate(baselines):
        p=tmp_path/relative
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(("reviewed generic source %d" % i).encode())
        p.chmod(0o444)
        monkeypatch.setattr(root,key,sha256(p.read_bytes()).hexdigest())
    monkeypatch.setattr(root,"TRUST",tmp_path)
    original=Path.lstat
    def attributed(path):
        result=original(path)
        if str(path).startswith(str(tmp_path)):
            if change and str(path).endswith(change[0]):
                mode=change[1] if isinstance(change[1],int) else result.st_mode
                uid=change[2] if len(change)>2 else 0
            else:
                mode=result.st_mode
                uid=0
            return SimpleNamespace(st_mode=mode,st_uid=uid)
        return result
    monkeypatch.setattr(Path,"lstat",attributed)
    return baselines


def test_three_pinned_root_sources_pass_with_readonly_evidence(tmp_path,monkeypatch,capsys):
    originals=fixture(tmp_path,monkeypatch)
    before={p:(tmp_path/p).read_bytes() for p,_ in originals}
    records=root.verify_installed_generic_controller()
    after={p:(tmp_path/p).read_bytes() for p,_ in originals}
    assert before==after
    assert len(records)==3
    assert [x["path"] for x in records]==[p for p,_ in originals]
    assert all(all(x["checks"].values()) for x in records)
    assert capsys.readouterr().out.count("PMV4_E_GENERIC_ROOT_FILE=")==3


def test_modified_source_sha_denied_with_specific_filename(tmp_path,monkeypatch,capsys):
    fixture(tmp_path,monkeypatch)
    p=tmp_path/"tools/independent_component_host_adapter.py"
    p.chmod(0o600)
    p.write_bytes(b"changed provider host adapter")
    p.chmod(0o444)
    with pytest.raises(root.Denied,match="INSTALLED_GENERIC_CONTROLLER_DRIFT:tools/independent_component_host_adapter.py"):
        root.verify_installed_generic_controller()
    out=capsys.readouterr().out
    assert '"exact_sha256": false' in out
    assert '"no_write_bits": true' in out


def test_wrong_uid_denied_without_loosening_mode(tmp_path,monkeypatch,capsys):
    fixture(tmp_path,monkeypatch,change=(
        "independent_component_release_root.py",0o100444,1000))
    with pytest.raises(root.Denied,match="INSTALLED_GENERIC_CONTROLLER_DRIFT:tools/independent_component_release_root.py"):
        root.verify_installed_generic_controller()
    assert '"uid_zero": false' in capsys.readouterr().out


def test_world_writable_source_denied(tmp_path,monkeypatch,capsys):
    fixture(tmp_path,monkeypatch,change=(
        "independent_component_release.py",0o100666,0))
    with pytest.raises(root.Denied,match="INSTALLED_GENERIC_CONTROLLER_DRIFT:tools/independent_component_release.py"):
        root.verify_installed_generic_controller()
    assert '"no_write_bits": false' in capsys.readouterr().out


def test_missing_trusted_source_denied(tmp_path,monkeypatch,capsys):
    fixture(tmp_path,monkeypatch)
    (tmp_path/"tools/independent_component_release.py").unlink()
    with pytest.raises(root.Denied,match="CONTROLLER_UNREADABLE"):
        root.verify_installed_generic_controller()
    assert "PMV4_E_GENERIC_ROOT_FILE_READ_DENIED" in capsys.readouterr().out


def test_symlinked_source_denied(tmp_path,monkeypatch,capsys):
    fixture(tmp_path,monkeypatch)
    p=tmp_path/"tools/independent_component_release.py"
    copy=tmp_path/"real.py"
    copy.write_bytes(p.read_bytes())
    p.unlink()
    p.symlink_to(copy)
    with pytest.raises(root.Denied,match="CONTROLLER_DRIFT"):
        root.verify_installed_generic_controller()
    assert '"not_symlink": false' in capsys.readouterr().out


def test_no_security_or_production_change():
    source=Path(root.__file__).read_text()
    assert "verify_installed_generic_controller()" in source
    for bad in ("chmod(", "os.chown(", "os.chmod(", "force_close_breaker", "systemctl stop"):
        assert bad not in source.split("def verify_installed_generic_controller",1)[1].split("def preflight",1)[0]


def test_untrusted_symlink_target_is_never_read(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    p=tmp_path/"tools/independent_component_release.py"
    target=tmp_path/"untrusted-sensitive-file"
    target.write_bytes(b"do-not-read-me")
    p.unlink()
    p.symlink_to(target)
    orig=Path.read_bytes
    def safe_read(candidate):
        if candidate==p or candidate==target:
            raise AssertionError("untrusted symlink target must not be read")
        return orig(candidate)
    monkeypatch.setattr(Path,"read_bytes",safe_read)
    with pytest.raises(root.Denied,match="INSTALLED_GENERIC_CONTROLLER_DRIFT"):
        root.verify_installed_generic_controller()



def test_all_three_production_hash_pins_match_exact_checked_in_controller_sources():
    """Catches any typo in production root pins before protected CI approval."""
    tree=Path(__file__).resolve().parents[2]
    for path,pinned in (
        ("tools/independent_component_release.py",root.CONTROLLER_SHA),
        ("tools/independent_component_host_adapter.py",root.ADAPTER_SHA),
        ("tools/independent_component_release_root.py",root.ROOT_ENTRY_SHA),
    ):
        actual=sha256((tree/path).read_bytes()).hexdigest()
        assert len(pinned)==64 and all(c in "0123456789abcdef" for c in pinned)
        assert actual==pinned, f"unreviewed or mistyped root SHA pin: {path}"
