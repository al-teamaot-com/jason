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
        result = ("external" if argv[3] == stage.STAGE_C_RUNTIME_HOST_FORMAT
                  else "healthy" if argv[3] == stage.STAGE_C_HEALTH_FORMAT
                  else "true")
        return SimpleNamespace(stdout=result+"\n", returncode=0)
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
    assert result["stage_c_independent_worker"]["live"] is True
    assert result["stage_c_independent_worker"]["root_acceptance_receipt_verified"] is False
    assert "STAGE_C_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK" in result["blocking_gates"]
    assert "STAGE_C_INDEPENDENT_WORKER_NOT_ACCEPTED" not in result["blocking_gates"]
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



def test_stage_c_embedded_or_unhealthy_still_blocks(tmp_path):
    def not_cutover(argv, **kwargs):
        if argv[0] == "/usr/bin/docker" and argv[3] in (
            stage.STAGE_C_RUNTIME_HOST_FORMAT, stage.STAGE_C_HEALTH_FORMAT,
        ):
            return SimpleNamespace(
                stdout="embedded\n" if argv[3] == stage.STAGE_C_RUNTIME_HOST_FORMAT
                else "unhealthy\n", returncode=0)
        return runner(argv, **kwargs)
    result = stage.inspect(policy=policy_fixture(tmp_path),
                           db=db_fixture(tmp_path), runner=not_cutover)
    assert result["stage_c_independent_worker"]["live"] is False
    assert "STAGE_C_INDEPENDENT_WORKER_NOT_ACCEPTED" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False


def test_stage_c_container_inspect_read_only_command_scope():
    allowed = [
        ["/usr/bin/docker", "inspect", "--format",
         stage.STAGE_C_RUNTIME_HOST_FORMAT, "jason-runtime"],
        ["/usr/bin/docker", "inspect", "--format",
         stage.STAGE_C_HEALTH_FORMAT, stage.STAGE_C_WORKER],
        ["/usr/bin/docker", "inspect", "--format",
         "{{.State.Running}}", stage.STAGE_C_WORKER],
    ]
    for args in allowed:
        assert stage.command(args, runner=runner) in ("external", "healthy", "true")
    for args in (
        ["/usr/bin/docker", "stop", stage.STAGE_C_WORKER],
        ["/usr/bin/docker", "inspect", "--format",
         "{{json .Config.Env}}", "jason-runtime"],
        ["/usr/bin/docker", "inspect", "--format",
         stage.STAGE_C_RUNTIME_HOST_FORMAT, stage.STAGE_C_WORKER],
        ["/usr/bin/docker", "inspect", "--format",
         stage.STAGE_C_HEALTH_FORMAT, "jason-runtime"],
    ):
        with pytest.raises(stage.RetirementEvidenceDenied):
            stage.command(args,runner=lambda *a,**k: (_ for _ in ()).throw(
                AssertionError("unsafe call attempted")))


def test_stage_d_live_read_only_does_not_waive_root_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(stage,"runbook_socket_status",lambda:{
        "registry_generation":0,"active_count":0,
        "provider_calls":False,"execution_authority":False,
        "configuration_mutations":False,
    })
    result=stage.inspect(policy=policy_fixture(tmp_path),
                         db=db_fixture(tmp_path),runner=runner)
    d=result["stage_d_independent_runbook_management"]
    assert d=={"unit_active":True,"unit_enabled":True,
               "socket_healthy":True,"registry_generation":0,"active_count":0,
               "live":True,"root_acceptance_receipt_verified":False}
    assert "STAGE_D_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK" in result["blocking_gates"]
    assert "STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED" not in result["blocking_gates"]
    assert result["governed_release_authorized"] is False
    assert result["service_mutations"] is False


def test_stage_d_inactive_or_bad_socket_is_not_accepted(tmp_path,monkeypatch):
    db=db_fixture(tmp_path)
    monkeypatch.setattr(stage,"runbook_socket_status",
                        lambda:(_ for _ in ()).throw(stage.RetirementEvidenceDenied("bad socket")))
    result=stage.inspect(policy=policy_fixture(tmp_path),
                         db=db,runner=runner)
    assert not result["stage_d_independent_runbook_management"]["live"]
    assert "STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED" in result["blocking_gates"]

    def stopped(argv,**kwargs):
        if argv[-1]==stage.STAGE_D_UNIT and "is-active" in argv:
            return SimpleNamespace(stdout="inactive\n",returncode=3)
        return runner(argv,**kwargs)
    result=stage.inspect(policy=policy_fixture(tmp_path),
                         db=db,runner=stopped)
    assert result["stage_d_independent_runbook_management"]["unit_active"] is False
    assert result["governed_release_authorized"] is False


def test_stage_d_prohibited_systemd_mutations_still_denied():
    for action in ("start","restart","stop","disable","enable","mask","reset-failed"):
        with pytest.raises(stage.RetirementEvidenceDenied):
            stage.command(["/usr/bin/systemctl",action,stage.STAGE_D_UNIT],
                          runner=lambda *a,**k: (_ for _ in ()).throw(
                              AssertionError("mutation must never run")))


def test_stage_d_unix_socket_same_uid_and_readonly_payload(tmp_path,monkeypatch):
    import os
    import socket
    import threading
    p=tmp_path/"read.sock"
    monkeypatch.setattr(stage,"STAGE_D_UID",os.getuid())
    received=[]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(p))
        p.chmod(0o600)
        server.listen(1)
        def serve():
            client,_=server.accept()
            with client:
                line=client.makefile("rb").readline()
                received.append(line)
                client.sendall((json.dumps({
                    "status":"healthy","registry_generation":0,"active_count":0,
                    "provider_calls":False,"configuration_mutations":False,
                    "execution_authority":False,
                })+"\n").encode())
        thread=threading.Thread(target=serve,daemon=True)
        thread.start()
        read=stage.runbook_socket_status(path=p)
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert received==[b'{"operation":"status"}\n']
    assert read=={"registry_generation":0,"active_count":0,
                  "provider_calls":False,"execution_authority":False,
                  "configuration_mutations":False}


def test_stage_d_unix_socket_wrong_mode_denied_before_connect(tmp_path,monkeypatch):
    import os
    import socket
    monkeypatch.setattr(stage,"STAGE_D_UID",os.getuid())
    p=tmp_path/"read.sock"
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(p))
        p.chmod(0o666)
        with pytest.raises(stage.RetirementEvidenceDenied,
                           match="RUNBOOK_SOCKET_UNTRUSTED"):
            stage.runbook_socket_status(path=p)


def test_stage_d_unix_socket_rejects_provider_authority_response(tmp_path,monkeypatch):
    import os
    import socket
    import threading
    monkeypatch.setattr(stage,"STAGE_D_UID",os.getuid())
    p=tmp_path/"read.sock"
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(p));p.chmod(0o600);server.listen(1)
        def serve():
            client,_=server.accept()
            with client:
                client.makefile("rb").readline()
                client.sendall((json.dumps({
                    "status":"healthy","registry_generation":0,"active_count":0,
                    "provider_calls":True,"configuration_mutations":False,
                    "execution_authority":False,
                })+"\n").encode())
        thread=threading.Thread(target=serve,daemon=True)
        thread.start()
        with pytest.raises(stage.RetirementEvidenceDenied,
                           match="RUNBOOK_READBACK_NOT_READONLY"):
            stage.runbook_socket_status(path=p)
        thread.join(timeout=3)
        assert not thread.is_alive()


def fake_root_pointer(monkeypatch, tmp_path, *, target=None, owner=0):
    ptr=tmp_path/"shadow-current"
    ptr.symlink_to("releases/"+(target or stage.STAGE_A1_SHA))
    original=Path.lstat
    def lstat(path):
        found=original(path)
        if path==ptr:
            return SimpleNamespace(st_mode=found.st_mode,st_uid=owner)
        return found
    monkeypatch.setattr(Path,"lstat",lstat)
    return ptr


def test_live_a1_immutable_source_exact_oci_memory_and_disconnected_network(
    tmp_path,monkeypatch,
):
    pointer=fake_root_pointer(monkeypatch,tmp_path)
    requests=[]
    def observed(argv,**kw):
        requests.append(argv)
        assert argv==[
            "/usr/bin/docker","inspect","--format",
            stage.STAGE_A1_SHADOW_FORMAT,stage.STAGE_A1_SHADOW,
        ]
        return SimpleNamespace(stdout=stage.STAGE_A1_SHADOW_EXPECTED+"\n",
                               returncode=0)
    result=stage.stage_a1_readback(pointer=pointer,runner=observed)
    assert result=={
        "pointer_exact":True,"shadow_healthy":True,
        "network_disconnected":True,"signed_image_pinned":True,
        "memory_bytes":4294967296,"live":True,
        "root_acceptance_receipt_verified":False,
    }
    assert len(requests)==1


@pytest.mark.parametrize("bad",[
    "healthy|2147483648|"+stage.STAGE_A1_IMAGE+"|true|none",
    "unhealthy|4294967296|"+stage.STAGE_A1_IMAGE+"|true|none",
    "healthy|4294967296|sha256:"+"f"*64+"|true|none",
    "healthy|4294967296|"+stage.STAGE_A1_IMAGE+"|true|bridge",
    "healthy|4294967296|"+stage.STAGE_A1_IMAGE+"|false|none",
    "healthy|unknown|"+stage.STAGE_A1_IMAGE+"|true|none",
    "healthy|4294967296|"+stage.STAGE_A1_IMAGE+"|true",
    "",
])
def test_a1_wrong_docker_readback_never_accepted(tmp_path,monkeypatch,bad):
    pointer=fake_root_pointer(monkeypatch,tmp_path)
    def observed(argv,**kw):
        return SimpleNamespace(stdout=bad+"\n",returncode=0 if bad else 1)
    result=stage.stage_a1_readback(pointer=pointer,runner=observed)
    assert result["pointer_exact"] is True
    assert result["root_acceptance_receipt_verified"] is False
    assert result["live"] is False


@pytest.mark.parametrize("target,owner",[
    ("f"*40,0),(None,1000),
])
def test_foreign_or_untrusted_release_pointer_blocks_docker_inspect(
    tmp_path,monkeypatch,target,owner,
):
    pointer=fake_root_pointer(monkeypatch,tmp_path,target=target,owner=owner)
    def denied(*a,**kw):
        raise AssertionError("Docker must not be queried for untrusted pointer")
    result=stage.stage_a1_readback(pointer=pointer,runner=denied)
    assert result["live"] is False
    assert result["pointer_exact"] is False


def test_stage_e_recognizes_live_a1_but_still_requires_root_receipts_and_parity(
    tmp_path,monkeypatch,
):
    monkeypatch.setattr(stage,"stage_a1_readback",lambda **kw:{
        "pointer_exact":True,"shadow_healthy":True,
        "network_disconnected":True,"signed_image_pinned":True,
        "memory_bytes":4294967296,"live":True,
        "root_acceptance_receipt_verified":False,
    })
    result=stage.inspect(policy=policy_fixture(tmp_path),db=db_fixture(tmp_path),
                         runner=runner)
    assert result["stage_a1_isolated_shadow"]["live"] is True
    assert "PMV4_A1_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK" in result["blocking_gates"]
    assert "PMV4_A1_ISOLATED_SHADOW_RELEASE_NOT_ACCEPTED" not in result["blocking_gates"]
    assert "PMV4_REPLACEMENT_CONTROLLER_PARITY_NOT_ACCEPTED" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False
    assert result["service_mutations"] is False
    assert result["provider_actions"] is False


def test_stage_e_a1_false_status_blocks_release_even_after_other_gates(
    tmp_path,monkeypatch,
):
    monkeypatch.setattr(stage,"stage_a1_readback",lambda **kw:{
        "pointer_exact":False,"shadow_healthy":False,
        "network_disconnected":False,"signed_image_pinned":False,
        "memory_bytes":None,"live":False,
        "root_acceptance_receipt_verified":False,
    })
    result=stage.inspect(policy=policy_fixture(tmp_path),db=db_fixture(tmp_path),
                         runner=runner)
    assert "PMV4_A1_ISOLATED_SHADOW_RELEASE_NOT_ACCEPTED" in result["blocking_gates"]
    assert result["governed_release_authorized"] is False


@pytest.mark.parametrize("args",[
    ["/usr/bin/docker","restart",stage.STAGE_A1_SHADOW],
    ["/usr/bin/docker","stop",stage.STAGE_A1_SHADOW],
    ["/usr/bin/docker","inspect","--format",stage.STAGE_A1_SHADOW_FORMAT,
     "jason-runtime"],
    ["/usr/bin/docker","inspect","--format","{{.Config.Env}}",
     stage.STAGE_A1_SHADOW],
])
def test_stage_e_docker_can_only_inspect_the_fixed_shadow_status(args):
    with pytest.raises(stage.RetirementEvidenceDenied):
        stage.command(args,runner=lambda *a,**k:
                      (_ for _ in ()).throw(AssertionError("forbidden")))
