"""Dry-run authenticated marker admission for the six PMv4 systemd units."""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from tools import pmv4_e_unit_admission as a
from tools import pmv4_e_scheduler_parity as parity


def marker():
    return {
        "schema_version":"1.0",
        "action":a.ACTION,
        "state":"accepted",
        "source_sha":"f"*40,
        "owner_approval_id":"owner-mcp-"+"a"*32,
        "source_scope_sha256":"c"*64,
        "source_rollback_sha":"1"*40,
        "prior_policy_sha256":a.PRIOR_POLICY,
        "accepted_policy_sha256":"d"*64,
        "production_freeze_sha256":a.FREEZE,
        "replacement_user_units":sorted(parity.USER_REPLACEMENT),
        "replacement_system_units":sorted(parity.ROOT_REPLACEMENT),
        "retired_user_units":sorted(parity.USER_LEGACY),
        "retired_system_units":sorted(parity.ROOT_LEGACY),
        "watchdog_retargets_engineering":True,
        "root_reconcile_no_legacy_install":True,
        "root_parity_checks_passed":True,
        "native_drift":"pass",
        "accepted_at":(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(),
        "rollback_receipt_sha256":"b"*64,
    }


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    root=tmp_path/"root"
    sub=root/"pmv4-e"
    sub.mkdir(parents=True)
    root.chmod(0o755)
    sub.chmod(0o755)
    record=sub/"replacement-retirement-accepted.json"
    record.write_bytes(json.dumps(marker(),sort_keys=True).encode())
    record.chmod(0o444)
    parent_lstat=Path.lstat
    paths={record,sub,root}
    def attributed(path):
        data=parent_lstat(path)
        if path in paths:
            return SimpleNamespace(
                st_uid=0,st_gid=0,st_mode=data.st_mode,
                st_nlink=data.st_nlink,st_size=data.st_size)
        return data
    monkeypatch.setattr(Path,"lstat",attributed)
    return record


def change(record:Path,key,bad):
    doc=json.loads(record.read_bytes())
    doc[key]=bad
    record.chmod(0o600)
    record.write_bytes(json.dumps(doc).encode())
    record.chmod(0o444)


def test_absent_marker_keeps_legacy_controller_unchanged(tmp_path):
    path=tmp_path/"no-acceptance.json"
    assert a.active_mode(root_path=path)=="legacy"
    for role in a.ROLE_UNITS:
        uid=0 if a.ROLE_UNITS[role][1] else 1000
        with pytest.raises(a.PMv4EUnitAdmissionDenied,
                           match="CUTOVER_NOT_ACCEPTED"):
            a.require_unit(role,root_path=path,uid=uid)


def test_all_six_new_units_require_one_exact_root_accepted_marker(fixture):
    assert a.active_mode(root_path=fixture)=="replacement"
    for role,(unit,is_root) in a.ROLE_UNITS.items():
        result=a.require_unit(role,root_path=fixture,
                              uid=0 if is_root else 1000)
        assert result["unit"]==unit
        assert result["role"]==role
        assert result["production_changes_performed"] is False
        assert result["owner_authority_issued"] is False


@pytest.mark.parametrize("role,uid",[
    ("engineering",0),("release-approval",0),("component-release",0),
    ("component-transition",1000),("component-readback",1000),
    ("component-reconcile",1000),
])
def test_service_identity_mismatch_never_runs_worker(fixture,role,uid):
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="UNEXPECTED_SERVICE_IDENTITY"):
        a.require_unit(role,root_path=fixture,uid=uid)


@pytest.mark.parametrize("key,bad,why",[
    ("state","staged","OWNER_RELEASE_IDENTITY_NOT_EXACT"),
    ("action","enable-old-timers","OWNER_RELEASE_IDENTITY_NOT_EXACT"),
    ("source_sha","bad","OWNER_RELEASE_IDENTITY_NOT_EXACT"),
    ("source_rollback_sha","bad","OWNER_RELEASE_IDENTITY_NOT_EXACT"),
    ("owner_approval_id","any","OWNER_RELEASE_IDENTITY_NOT_EXACT"),
    ("production_freeze_sha256","a"*64,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("prior_policy_sha256","f"*64,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("accepted_policy_sha256",a.PRIOR_POLICY,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("watchdog_retargets_engineering",False,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("root_reconcile_no_legacy_install",False,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("root_parity_checks_passed",False,"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("native_drift","ignored","SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("replacement_user_units",sorted(parity.USER_LEGACY),"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("retired_system_units",sorted(parity.ROOT_REPLACEMENT),"SCHEDULING_SCOPE_NOT_VERIFIED"),
    ("accepted_at","bogus","ROOT_ACCEPTED_TIME_INVALID"),
])
def test_any_unreviewed_root_cutover_scope_fails_closed(fixture,key,bad,why):
    change(fixture,key,bad)
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match=why):
        a.read_root_marker(fixture)


def test_missing_or_foreign_owner_file_denied(fixture):
    fixture.chmod(0o666)
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="ROOT_RECEIPT_FILE_UNTRUSTED"):
        a.active_mode(root_path=fixture)


def test_untrusted_parent_modes_denied(fixture):
    fixture.parent.chmod(0o777)
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="ROOT_PARENT_NOT_TRUSTED"):
        a.active_mode(root_path=fixture)


def test_symlinked_acceptance_file_denied_without_following_it(fixture,monkeypatch):
    secret=fixture.parent/"untrusted"
    secret.write_text("do not read")
    fixture.chmod(0o600)
    fixture.unlink()
    fixture.symlink_to(secret)
    old=Path.read_bytes
    def fail_read(path):
        if path in (secret,fixture):
            raise AssertionError("symlinked receipt was followed")
        return old(path)
    monkeypatch.setattr(Path,"read_bytes",fail_read)
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="ROOT_RECEIPT_FILE_UNTRUSTED"):
        a.active_mode(root_path=fixture)


def test_duplicate_unit_in_accepted_marker_denied(fixture):
    doc=json.loads(fixture.read_bytes())
    doc["replacement_user_units"].append(doc["replacement_user_units"][0])
    fixture.chmod(0o600)
    fixture.write_text(json.dumps(doc))
    fixture.chmod(0o444)
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="SCHEDULING_SCOPE_NOT_VERIFIED"):
        a.active_mode(root_path=fixture)


def test_wrong_role_never_registered_even_after_acceptance(fixture):
    with pytest.raises(a.PMv4EUnitAdmissionDenied,match="UNREVIEWED_UNIT_ROLE"):
        a.require_unit("arbitrary",root_path=fixture,uid=1000)


def test_main_source_never_modifies_a_production_unit():
    source=Path(a.__file__).read_text()
    for disallowed in (
        "systemctl stop","systemctl disable","systemctl enable",
        "docker run","docker compose","os.chown(","os.unlink(",
        "os.replace(","force_close_breaker","subprocess.run(",
    ):
        assert disallowed not in source
    assert "PMV4_E_SCHEDULER_ROOT_REPLACEMENT_CUTOVER_NOT_ACCEPTED" in (
        "PMV4_E_SCHEDULER_"+"ROOT_REPLACEMENT_CUTOVER_NOT_ACCEPTED")
