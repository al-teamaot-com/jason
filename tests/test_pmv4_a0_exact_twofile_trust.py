"""Nonprivileged tests of reviewed exact-Owner A0 root-trust migration."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest
from tools import pmv4_a0_exact_twofile_root_trust_migrator as migration
from tools import pmv4_a0_exact_twofile_owner_issuer as issuer

ROOT = Path(__file__).resolve().parents[1]


def checked_packet(monkeypatch):
    real = migration.secure_read
    def patched(path, *, owner, mode, limit=200000):
        if path == migration.ROOT:
            return (ROOT / "tools/pmv4_a0_exact_twofile_root_trust_migrator.py").read_bytes()
        return real(path, owner=owner, mode=mode, limit=limit)
    monkeypatch.setattr(migration, "secure_read", patched)
    return migration.source_packet()


def test_source_only_package_binds_exact_two_targets(monkeypatch):
    p, contents = checked_packet(monkeypatch)
    assert p["scope_sha256"] == issuer.EXPECTED_SCOPE
    assert set(contents) == {(0, "old"), (1, "old"), (0, "new"), (1, "new")}
    assert [migration.digest(contents[(i, "old")]) for i in range(2)] == list(migration.OLD)
    assert [migration.digest(contents[(i, "new")]) for i in range(2)] == list(migration.NEW)


def test_corrupt_archive_denied_before_execution(monkeypatch):
    real = migration.secure_read
    def modified(path, *, owner, mode, limit=200000):
        if path == migration.ROOT:
            return (ROOT / "tools/pmv4_a0_exact_twofile_root_trust_migrator.py").read_bytes()
        value = real(path, owner=owner, mode=mode, limit=limit)
        return value + b"tamper" if path == migration.PACKAGE else value
    monkeypatch.setattr(migration, "secure_read", modified)
    with pytest.raises(migration.TrustMigrationDenied, match="PACKAGE_DRIFT"):
        migration.source_packet()


def test_untrusted_manifest_scope_denied(monkeypatch):
    real = migration.secure_read
    def modified(path, *, owner, mode, limit=200000):
        if path == migration.ROOT:
            return (ROOT / "tools/pmv4_a0_exact_twofile_root_trust_migrator.py").read_bytes()
        if path == migration.MANIFEST:
            obj=json.loads(real(path,owner=owner,mode=mode,limit=limit))
            obj["candidate_sha"]="f"*40
            return migration.canonical(obj)
        return real(path,owner=owner,mode=mode,limit=limit)
    monkeypatch.setattr(migration, "secure_read", modified)
    with pytest.raises(migration.TrustMigrationDenied, match="REVIEWED_MANIFEST_CHANGED"):
        migration.source_packet()


def test_direct_checkout_cannot_run_root_migration():
    with pytest.raises(migration.TrustMigrationDenied, match="INSTALLED_ISOLATED_ROOT"):
        migration.trust_entry()


def test_owner_review_requires_exact_files_and_no_existing_proof():
    assert issuer.review()["root_executor_sha256"] == sha256(
        (ROOT / "tools/pmv4_a0_exact_twofile_root_trust_migrator.py").read_bytes()
    ).hexdigest()
    assert not issuer.PROOF.exists()


def test_exact_file_replace_and_reverse_recovery_sandbox(tmp_path, monkeypatch):
    _, data=checked_packet(monkeypatch)
    files=[tmp_path/"ci.py",tmp_path/"policy.json"]
    mode=[0o444,0o400]
    for i,f in enumerate(files):
        f.write_bytes(data[(i,"old")]);f.chmod(mode[i])
    def read(path, *, owner, mode, limit=200000):
        assert owner==0
        assert path.stat().st_mode & 0o777 == mode
        return path.read_bytes()
    monkeypatch.setattr(migration,"secure_read",read)
    monkeypatch.setattr(migration,"TARGETS",tuple(zip(files,mode)))
    monkeypatch.setattr(migration.os,"fchown",lambda *args:None)
    for i,f in enumerate(files):
        migration.replace_exact(f,data[(i,"old")],data[(i,"new")],mode[i])
    assert [migration.digest(f.read_bytes()) for f in files]==list(migration.NEW)
    migration.rollback_exact(data)
    assert [migration.digest(f.read_bytes()) for f in files]==list(migration.OLD)


def test_recovery_refuses_foreign_modified_bytes(tmp_path,monkeypatch):
    _, data=checked_packet(monkeypatch)
    f=tmp_path/"ci.py"
    f.write_bytes(b"foreign modification");f.chmod(0o444)
    monkeypatch.setattr(migration,"TARGETS",((f,0o444),))
    monkeypatch.setattr(migration,"secure_read",
                        lambda p,*,owner,mode,limit=200000:p.read_bytes())
    with pytest.raises(migration.TrustMigrationDenied,
                       match="ROLLBACK_FOREIGN_INODE_OR_BYTES"):
        migration.rollback_exact(data)
    assert f.read_bytes()==b"foreign modification"


def test_one_owner_launcher_only_offers_exact_modes():
    script=(ROOT/"tools/pmv4_a0_exact_twofile_owner_local.sh").read_text()
    for source in ("pmv4_a0_exact_twofile_owner_issuer.py",
                   "pmv4_a0_exact_twofile_root_trust_migrator.py"):
        assert source in script
    assert sha256((ROOT/"tools/pmv4_a0_exact_twofile_owner_issuer.py").read_bytes()
                  ).hexdigest() in script
    assert sha256((ROOT/"tools/pmv4_a0_exact_twofile_root_trust_migrator.py").read_bytes()
                  ).hexdigest() in script
    result=subprocess.run(["bash",str(ROOT/"tools/pmv4_a0_exact_twofile_owner_local.sh"),
                           "--check-only"],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert "ROOT_WRITES=false" in result.stdout
