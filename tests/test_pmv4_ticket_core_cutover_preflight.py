"""Independent Stage C data and mount safety checks, no production mutation."""
from pathlib import Path
import os
import sqlite3

import pytest

from tools import pmv4_ticket_core_cutover_preflight as gate


@pytest.fixture
def ledger(tmp_path):
    p=tmp_path/"autonomy-operational-work.sqlite3"
    conn=sqlite3.connect(p)
    conn.execute("CREATE TABLE autonomy_ticket_scan_cycle (scanned_at TEXT, provider_items INTEGER, duplicate_items INTEGER, evaluated INTEGER)")
    for i in range(3):
        conn.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?)",
                     (f"2026-11-16T12:0{i}:00Z",162,0,161))
    conn.commit()
    conn.close()
    p.chmod(0o600)
    lock=p.with_name(p.name+".owner.lock")
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    return p,lock


def test_same_ledger_and_lock_inode_required(ledger):
    p,lock=ledger
    assert gate.check_same_canonical_files(p,p,uid=os.geteuid()) == {
        "same_ledger_inode":True,"same_lock_inode":True,
        "same_filesystem":True}
    separate=p.parent/"other.sqlite3"
    separate.write_bytes(p.read_bytes())
    separate.chmod(0o600)
    separate_lock=separate.with_name(separate.name+".owner.lock")
    separate_lock.touch(mode=0o600)
    separate_lock.chmod(0o600)
    with pytest.raises(gate.CoreCutoverDenied,match="LEDGER_INODE_DIFFERENT"):
        gate.check_same_canonical_files(p,separate,uid=os.geteuid())


def test_separate_lock_inode_fails_even_with_shared_db(ledger,monkeypatch):
    p,lock=ledger
    original=gate.identity
    external=p.parent/"external.sqlite3"
    def mapped(path,**kw):
        if path == external:
            original_value=original(p,**kw)
            return gate.FileIdentity(str(external),original_value.device,
                                     original_value.inode,original_value.uid,
                                     original_value.mode)
        if path == external.with_name(external.name+".owner.lock"):
            old=original(lock,**kw)
            return gate.FileIdentity(str(path),old.device,old.inode+1,
                                     old.uid,old.mode)
        return original(path,**kw)
    monkeypatch.setattr(gate,"identity",mapped)
    with pytest.raises(gate.CoreCutoverDenied,match="LOCK_INODE_DIFFERENT"):
        gate.check_same_canonical_files(p,external,uid=os.geteuid())


def test_untrusted_symlink_or_mode_refused(ledger):
    p,lock=ledger
    p.chmod(0o644)
    with pytest.raises(gate.CoreCutoverDenied,match="INODE_UNTRUSTED"):
        gate.identity(p,uid=os.geteuid())
    p.chmod(0o600)
    alias=p.parent/"alias.sqlite3"
    alias.symlink_to(p)
    with pytest.raises(gate.CoreCutoverDenied,match="PATH_UNTRUSTED"):
        gate.identity(alias,uid=os.geteuid())


def test_scan_evidence_distinct_and_content_free(ledger):
    p,_=ledger
    result=gate.read_scan_evidence(p)
    assert result == {
        "cycle_count":3, "distinct_cycle_count":3, "duplicate_items":0,
        "minimum_evaluated":161, "customer_data_included":False,
    }


def test_scan_duplicate_and_short_history_fail(ledger):
    p,_=ledger
    conn=sqlite3.connect(p)
    conn.execute("UPDATE autonomy_ticket_scan_cycle SET duplicate_items=1 WHERE scanned_at LIKE '%01:00%'")
    conn.commit()
    conn.close()
    with pytest.raises(gate.CoreCutoverDenied,match="SCAN_CONTINUITY"):
        gate.read_scan_evidence(p)
    conn=sqlite3.connect(p)
    conn.execute("DELETE FROM autonomy_ticket_scan_cycle")
    conn.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES ('x',2,0,1)")
    conn.commit()
    conn.close()
    with pytest.raises(gate.CoreCutoverDenied,match="SCAN_CONTINUITY"):
        gate.read_scan_evidence(p)


def valid_mount():
    return {"Destination":"/var/lib/jason/ticket-core",
            "Source":"/var/lib/jason/ticket-core",
            "Type":"bind","RW":True}


def test_dedicated_only_state_mount_allowed():
    assert gate.validate_future_mounts([valid_mount()]) is True
    with pytest.raises(gate.CoreCutoverDenied,match="UNREVIEWED_MOUNT"):
        gate.validate_future_mounts([valid_mount(),{
            "Destination":"/app","Source":"/opt/jason/release-code",
            "Type":"bind","RW":False}])


@pytest.mark.parametrize("mutate,reason",[
    (lambda x:x.update({"Source":"/var/lib/jason/openclaw"}),"SHARED_STATE"),
    (lambda x:x.update({"Source":"/var/lib/jason/openclaw/autonomy-operational-work.sqlite3"}),"SHARED_STATE"),
    (lambda x:x.update({"Destination":"/run/jason-secrets/openbao"}),"SECRETS"),
    (lambda x:x.update({"Type":"volume"}),"NOT_RW_BIND"),
    (lambda x:x.update({"RW":False}),"NOT_RW_BIND"),
    (lambda x:x.update({"Source":"../untrusted"}),"PATH_UNTRUSTED"),
    (lambda x:x.update({"Destination":"/var/lib/jason/ticket-core/../openclaw"}),"PATH_UNTRUSTED"),
])
def test_unsafe_legacy_state_mount_denied(mutate,reason):
    mount=valid_mount()
    mutate(mount)
    with pytest.raises(gate.CoreCutoverDenied,match=reason):
        gate.validate_future_mounts([mount])


def test_extra_writable_mount_denied():
    with pytest.raises(gate.CoreCutoverDenied,match="UNREVIEWED_MOUNT"):
        gate.validate_future_mounts([valid_mount(),{
            "Destination":"/etc/unrelated","Source":"/srv/unrelated",
            "Type":"bind","RW":True}])


def test_no_mount_denied():
    with pytest.raises(gate.CoreCutoverDenied,match="MOUNT_REQUIRED"):
        gate.validate_future_mounts([])


def test_legacy_observation_explicitly_blocks_cutover(ledger,monkeypatch):
    p,lock=ledger
    monkeypatch.setattr(gate,"OLD_LEDGER",p)
    original=gate.identity
    monkeypatch.setattr(gate,"identity",
                        lambda path,**kw: original(path,uid=os.geteuid()))
    row=gate.observe_legacy_baseline()
    assert row["status"]=="read_only_baseline_verified"
    assert row["external_cutover_authorized"] is False
    assert row["external_cutover_ready"] is False
    assert row["production_mutations"] is False
    assert row["scan_evidence"]["cycle_count"] == 3
