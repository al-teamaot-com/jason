"""Source-only tests for two exact audit-health systemd drop-ins."""
import os
from pathlib import Path

import pytest

from tools import audit_journal_health_wal_sandbox as p


def test_only_two_exact_health_units_and_no_service_or_approval_mutations():
    result = p.render_dropins()
    assert set(result) == set(p.UNITS)
    assert p.DROPIN_NAME == "96-audit-journal-wal-health.conf"
    assert len(set(result.values())) == 1
    for raw in result.values():
        text = raw.decode("ascii")
        assert text.startswith("[Service]\n")
        assert "ReadWritePaths=" + str(p.ROOT) + "\n" in text
        assert "ReadOnlyPaths=" + str(p.ACTIVE) + " " in text
        for name in p.SIBLING_DBS:
            assert str(p.ROOT / name) in text
        assert "InaccessiblePaths=-" + str(p.ROOT / p.NON_DB_ENTRY) in text
        assert "ExecStart" not in text
        assert "User=" not in text
        assert "RootDirectory=" not in text
        assert "Environment=" not in text
        assert "Restart=" not in text
        assert "ReadWritePaths=/" not in text.replace(
            "ReadWritePaths=" + str(p.ROOT) + "\n", "")
        assert "*" not in text and "?" not in text


def staged(tmp_path):
    os.chmod(tmp_path, 0o700)
    (tmp_path / p.NON_DB_ENTRY).mkdir()
    for name in (p.ACTIVE.name, *p.SIBLING_DBS):
        row = tmp_path / name
        row.write_bytes(b"synthetic")
        os.chmod(row, 0o600)
    return tmp_path


def test_fixed_live_inventory_synthetic(tmp_path):
    directory = staged(tmp_path)
    assert p.reviewed_inventory(directory, writer_uid=os.getuid())["no_unknown_entries"]
    aux = directory / (p.ACTIVE.name + "-shm")
    aux.write_bytes(b"synthetic")
    os.chmod(aux, 0o600)
    assert aux.name in p.reviewed_inventory(directory, writer_uid=os.getuid())["reviewed_entries"]


def test_unknown_entries_symlink_and_broadened_modes_fail_closed(tmp_path):
    d = staged(tmp_path)
    other = d / "new-business.sqlite3"
    other.write_bytes(b"new")
    with pytest.raises(p.SandboxPolicyError, match="UNKNOWN"):
        p.reviewed_inventory(d, writer_uid=os.getuid())
    other.unlink()
    os.chmod(d / p.ACTIVE.name, 0o644)
    with pytest.raises(p.SandboxPolicyError, match="DB_IDENTITY"):
        p.reviewed_inventory(d, writer_uid=os.getuid())
    os.chmod(d / p.ACTIVE.name, 0o600)
    aux = d / (p.ACTIVE.name + "-shm")
    aux.symlink_to(d / p.ACTIVE.name)
    with pytest.raises(p.SandboxPolicyError, match="AUX_IDENTITY"):
        p.reviewed_inventory(d, writer_uid=os.getuid())


def test_directory_scope_cannot_be_relaxed_without_fail_closed_check(tmp_path):
    d = staged(tmp_path)
    os.chmod(d, 0o770)
    with pytest.raises(p.SandboxPolicyError, match="DIRECTORY"):
        p.reviewed_inventory(d, writer_uid=os.getuid())


def test_source_renderer_never_invokes_privileged_action():
    # No host reads or root changes are performed by rendering the policy.
    assert p.render_dropins() == p.render_dropins()


def test_real_sqlite_wal_requires_auxiliary_creation_when_directory_is_readonly(tmp_path):
    """Real SQLite reproduction only; this is NOT a systemd root sandbox test."""
    import sqlite3
    if os.geteuid() == 0:
        pytest.skip("POSIX root bypasses parent mode restrictions")
    d = tmp_path / "repro"
    d.mkdir()
    active = d / "active.sqlite3"
    con = sqlite3.connect(str(active))
    assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    con.execute("CREATE TABLE synthetic_only(i integer)")
    con.execute("INSERT INTO synthetic_only VALUES (1)")
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    assert not (d / "active.sqlite3-wal").exists()
    assert not (d / "active.sqlite3-shm").exists()
    os.chmod(active, 0o400)
    os.chmod(d, 0o500)
    try:
        import sqlite3
        with pytest.raises(sqlite3.OperationalError):
            db = sqlite3.connect("file:" + str(active) + "?mode=ro", uri=True)
            try:
                db.execute("PRAGMA cache_size=-65536")
                db.execute("SELECT COUNT(*) FROM synthetic_only").fetchone()
            finally:
                db.close()
    finally:
        os.chmod(d, 0o700)
    db = sqlite3.connect("file:" + str(active) + "?mode=ro", uri=True)
    try:
        assert db.execute("SELECT COUNT(*) FROM synthetic_only").fetchone() == (1,)
    finally:
        db.close()
    assert (d / "active.sqlite3-shm").exists()
    assert (d / "active.sqlite3-wal").exists()


def test_systemd_syntax_of_both_overlays(tmp_path):
    """Parser validation, not evidence of enforced mount namespaces."""
    import shutil
    import subprocess
    analyzer = shutil.which("systemd-analyze")
    if not analyzer:
        pytest.skip("systemd-analyze not available")
    units = p.render_dropins()
    for name, blob in units.items():
        unitfile = tmp_path / name
        unitfile.write_text("[Unit]\nDescription=Isolated WAL sandbox parser check\n"
                            "[Service]\nType=oneshot\nExecStart=/usr/bin/true\n")
        overlay = tmp_path / (name + ".d") / p.DROPIN_NAME
        overlay.parent.mkdir()
        overlay.write_bytes(blob)
        proc = subprocess.run([analyzer, "verify", str(unitfile)],
                              capture_output=True, text=True, timeout=10)
        assert proc.returncode == 0, (name, proc.stdout, proc.stderr)
