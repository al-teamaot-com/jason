"""Stage E retirement admission is a read-only negative gate, not an installer."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from tools import pmv4_e_retirement_readiness as stage


def test_default_ticket_ledger_uses_canonical_stage_c_location():
    assert stage.TICKET_LEDGER == Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")


def runner(argv, **kwargs):
    assert kwargs["check"] is False
    assert kwargs["timeout"] == 12
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    if "--user" in argv:
        assert kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"
    if argv[0] == "/usr/bin/docker":
        return SimpleNamespace(stdout="true\n",returncode=0)
    return SimpleNamespace(stdout="active\n" if "is-active" in argv else "enabled\n",
                           returncode=0)


def db_fixture(tmp_path, *, age_seconds=30, duplicates=0):
    db=tmp_path/"work.sqlite3"
    con=sqlite3.connect(db)
    con.execute("CREATE TABLE autonomy_ticket_scan_cycle (scanned_at TEXT,provider_items INTEGER,duplicate_items INTEGER,evaluated INTEGER)")
    moment=(datetime.now(timezone.utc)-timedelta(seconds=age_seconds)).isoformat()
    con.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?)",
                (moment,160,duplicates,159))
    con.commit()
    con.close()
    return db


def policy_fixture(tmp_path):
    p=tmp_path/"desired.json"
    p.write_text(json.dumps({"schema_version":"1.0",
                             "required_user_units":list(stage.USER_LEGACY),
                             "required_system_units":list(stage.SYSTEM_LEGACY)}))
    return p


def test_end_to_end_source_only_never_claims_retirement(tmp_path):
    result=stage.inspect(policy=policy_fixture(tmp_path),
                         current=tmp_path/"missing-pointer",
                         db=db_fixture(tmp_path),runner=runner)
    assert result["status"]=="not_ready_for_pmv3_retirement"
    assert result["source_policy_legacy_required"] is True
    assert result["legacy_observation_complete"] is True
    assert result["legacy_active"] is True
    assert result["required_monitoring_active"] is True
    assert all(result["protected_containers_running"].values())
    assert result["ticket_scan"]["status"]=="fresh"
    assert "LEGACY_ENG_AND_RELEASE_CONTROLLERS_STILL_ACTIVE" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False
    assert result["service_mutations"] is False
    assert result["provider_actions"] is False
    assert result["ticket_mutations"] is False


@pytest.mark.parametrize("argv",[
    ["/usr/bin/systemctl","stop","jason-release-manager.timer"],
    ["/usr/bin/systemctl","--user","disable","jason-release-manager.timer"],
    ["/usr/bin/systemctl","restart","jason-production-drift-watchdog.timer"],
    ["/usr/bin/docker","stop","jason-runtime"],
    ["/usr/bin/docker","inspect","--format","{{.State.Running}}","unreviewed"],
    ["/bin/sh","-c","true"],
])
def test_mutating_or_unrelated_command_never_invoked(argv):
    def forbidden(*args,**kwargs):
        raise AssertionError("unsafe command reached runner")
    with pytest.raises(stage.RetirementEvidenceDenied):
        stage.command(argv,runner=forbidden)


def test_no_live_ticket_copy_and_stale_duplicate_rejected(tmp_path):
    recent=db_fixture(tmp_path)
    assert stage.scan_summary(recent)["status"]=="fresh"
    old=tmp_path/"old"
    old.mkdir()
    stale=db_fixture(old,age_seconds=700)
    assert stage.scan_summary(stale)["status"]=="stale"


def test_duplicate_scan_denies_success(tmp_path):
    db=db_fixture(tmp_path,duplicates=1)
    assert stage.scan_summary(db)["status"]=="unverified"


def test_unavailable_user_unit_fails_closed(tmp_path):
    def no_user(argv,**kw):
        if "--user" in argv:
            return SimpleNamespace(stdout="",returncode=1)
        return runner(argv,**kw)
    result=stage.inspect(policy=policy_fixture(tmp_path),
                         db=db_fixture(tmp_path),runner=no_user)
    assert result["legacy_observation_complete"] is False
    assert "LEGACY_SYSTEMD_UNIT_READBACK_UNVERIFIED" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False


def test_missing_source_policy_refused(tmp_path):
    with pytest.raises(stage.RetirementEvidenceDenied,match="SOURCE_POLICY_UNAVAILABLE"):
        stage.inspect(policy=tmp_path/"missing.json",runner=runner)


def test_unit_readback_read_only_from_three_groups():
    d=stage.units_readback(runner=runner)
    assert len(d["legacy_user"])==len(stage.USER_LEGACY)
    assert len(d["legacy_system"])==len(stage.SYSTEM_LEGACY)
    assert len(d["continuity"])==len(stage.REQUIRED_CONTINUITY)
    assert all(x["enabled"]=="enabled" for group in d.values() for x in group)
