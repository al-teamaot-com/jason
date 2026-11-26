from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path

import pytest

from tools import pmv4_c_host_consumer_projection as p


def test_five_exact_host_units_and_nine_existing_environment_rebinds():
    assert set(p.SERVICE_ENV)=={
        "jason-usage-exporter.service",
        "jason-usage-attribution-exporter.service",
        "jason-security-control-exporter.service",
        "jason-reflection-exporter.service",
        "jason-resolution-memory-exporter.service",
    }
    assert sum(map(len,p.SERVICE_ENV.values()))==9
    assert set(p.DB_FILES)=={
        "JASON_MODEL_USAGE_DB","JASON_ORCHESTRATION_EVENTS_DB",
        "JASON_TEAMS_IDENTITY_BINDINGS_DB","JASON_REFLECTION_DB",
        "JASON_RESOLUTION_MEMORY_DB",
    }
    assert all(p.exact_canonical_path(k).parent==p.SHARED for k in p.DB_FILES)


def test_exact_dropin_has_no_other_mutations_or_credential_projection():
    for unit,blob in p.all_dropins().items():
        txt=blob.decode("ascii")
        lines=txt.splitlines()
        assert txt.endswith("\n") and lines[1]=="[Service]"
        assert lines.count("ReadOnlyPaths=")==1
        assert lines.count("ReadOnlyPaths=/opt/jason/current "+(
            " ".join(str(p.exact_canonical_path(k))
                     for k in p.SERVICE_ENV[unit])
        ))==1
        assert sum(line.startswith("Environment=") for line in lines)==len(p.SERVICE_ENV[unit])
        assert not any(line.startswith(x) for line in lines for x in (
            "ExecStart","User=","Group=","Restart=","LoadCredential=",
            "ReadWritePaths=","BindPaths=","BindReadOnlyPaths=","NetworkNamespacePath=",
            "CapabilityBoundingSet=","AmbientCapabilities=",
        ))
        assert all("/var/lib/jason/openclaw" not in line for line in lines)
        assert not any(word in txt.lower() for word in (
            "secret-id", "role-id", "token", "password", "client_secret",
        ))


def test_source_fragment_bytes_match_live_authoritative_shipped_files():
    base=Path(__file__).resolve().parents[1]
    for unit in p.SERVICE_ENV:
        source=(base/p.FRAGMENTS/unit)
        assert source.is_file()
        raw=source.read_bytes()
        assert raw.startswith(b"[Unit]\n")
        assert raw.count(b"\n[Service]\n")==1
        for key in p.SERVICE_ENV[unit]:
            needle=b"Environment="+key.encode()+b"="+(
                str(p.LEGACY/p.DB_FILES[key])).encode()
            assert raw.count(needle)==1
        assert p.verify_fragment_bytes(source,source,require_root=False)==(
            sha256(raw).hexdigest()
        )


def test_fragment_drift_rejected_without_modification(tmp_path):
    base=Path(__file__).resolve().parents[1]
    filename="jason-reflection-exporter.service"
    source=base/p.FRAGMENTS/filename
    installed=tmp_path/filename
    installed.write_bytes(source.read_bytes()+b"\n# unexpected edit\n")
    before=installed.read_bytes()
    with pytest.raises(p.HostProjectionDenied,match="DRIFT"):
        p.verify_fragment_bytes(source,installed,require_root=False)
    assert installed.read_bytes()==before


def test_source_symlink_rejected(tmp_path):
    base=Path(__file__).resolve().parents[1]
    filename="jason-usage-exporter.service"
    link=tmp_path/filename
    link.symlink_to(base/p.FRAGMENTS/filename)
    with pytest.raises(p.HostProjectionDenied,match="NOT_REGULAR"):
        p.verify_fragment_bytes(link,base/p.FRAGMENTS/filename,require_root=False)


def test_unknown_unit_and_untrusted_environment_rejected():
    with pytest.raises(p.HostProjectionDenied,match="UNREVIEWED_SYSTEMD_UNIT"):
        p.render_dropin("jason-runtime.service")
    with pytest.raises(p.HostProjectionDenied,match="UNREVIEWED_DB_ENV"):
        p.exact_canonical_path("JASON_OWNER_SIGNING_KEY")


def test_canonical_file_preflight_denies_both_or_neither(tmp_path,monkeypatch):
    shared=tmp_path/"shared";legacy=tmp_path/"old"
    shared.mkdir(mode=0o700);legacy.mkdir(mode=0o700)
    monkeypatch.setattr(p,"SHARED",shared)
    monkeypatch.setattr(p,"LEGACY",legacy)
    name=next(iter(p.DB_FILES.values()))
    file=shared/name
    file.write_bytes(b"safe")
    file.chmod(0o600)
    # Other four are absent; first file must be valid, no mutating SQL call.
    with pytest.raises(FileNotFoundError):
        p.assert_canonical_files(uid=os.getuid())
    legacy_file=legacy/name
    legacy_file.write_bytes(b"duplicate")
    with pytest.raises(p.HostProjectionDenied,match="SPLIT_BRAIN"):
        p.assert_canonical_files(uid=os.getuid())


def test_canonical_file_preflight_real_exact_modes_and_inodes(tmp_path,monkeypatch):
    shared=tmp_path/"shared";legacy=tmp_path/"old"
    shared.mkdir(mode=0o700);legacy.mkdir(mode=0o700)
    monkeypatch.setattr(p,"SHARED",shared)
    monkeypatch.setattr(p,"LEGACY",legacy)
    for name in p.DB_FILES.values():
        f=shared/name;f.write_bytes(b"synthetic");f.chmod(0o600)
    result=p.assert_canonical_files(uid=os.getuid())
    assert set(result)==set(p.DB_FILES.values())
    for name,info in result.items():
        file=shared/name
        assert info==(file.stat().st_dev,file.stat().st_ino)
    (shared/"reflection.sqlite3").chmod(0o644)
    with pytest.raises(p.HostProjectionDenied,match="UNTRUSTED"):
        p.assert_canonical_files(uid=os.getuid())
