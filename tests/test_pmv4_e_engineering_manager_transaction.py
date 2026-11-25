"""Provider-free transaction failure and rollback tests."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import pytest

from tools import pmv4_e_engineering_manager_transaction as m

ROOT = Path(__file__).resolve().parents[1]


def plan():
    return {"action": m.ACTION, "policy": {"candidate_sha": "a"*40, "rollback_sha": m.LKG},
            "old_user_timers": list(m.TIMERS), "new_system_timers": list(m.TIMERS),
            "services": list(m.SERVICES), "production_authority": False, "provider_writes": False,
            "runtime_or_mcp_restart_allowed": False, "freeze_or_hold_change": False,
            "monitoring_restart": "jason-production-health-exporter.service",
            "pause_preserved_during_cutover": True, "rollback_authorized": True}


class Fixture:
    ordered = ("verify_owner_and_before", "persist_before_images", "stop_old_timers",
               "verify_old_services_quiescent", "publish_files_without_receipt", "reload_managers",
               "verify_old_units_retired", "enable_new_system_timers", "verify_new_timers",
               "restart_exact_monitoring_exporter", "verify_approved_monitoring_expectations",
               "publish_exact_native_receipt", "verify_successor_topology_and_source",
               "verify_preserved_pause_and_controls", "verify_native_drift_and_lkg",
               "record_cutover_verified")
    def __init__(self, fail=None, approved=True):
        self.events=[]; self.fail=fail; self.approved=approved
    def __getattr__(self,name):
        def call(*args):
            self.events.append(name)
            if self.fail==name: raise RuntimeError("injected failure")
            if name=="verify_owner_and_before": return self.approved
        return call


def test_exact_cutover_order_no_duplicate_trigger():
    a=Fixture(); p=plan(); before=deepcopy(p)
    m.migrate(a,p,m.verify_plan(p))
    assert a.events==list(Fixture.ordered)
    assert p==before
    assert a.events.index("verify_old_units_retired")<a.events.index("enable_new_system_timers")
    assert a.events.index("verify_new_timers")<a.events.index("publish_exact_native_receipt")
    assert a.events.index("verify_native_drift_and_lkg")<a.events.index("record_cutover_verified")


@pytest.mark.parametrize("stage",Fixture.ordered[2:])
def test_every_mutating_boundary_rolls_back(stage):
    a=Fixture(fail=stage); p=plan()
    with pytest.raises(RuntimeError,match="injected"):
        m.migrate(a,p,m.verify_plan(p))
    assert a.events[-3:]==["restore_before_images_and_topology",
                           "verify_rollback_and_preserved_controls","record_rollback"]
    if stage!="record_cutover_verified": assert "record_cutover_verified" not in a.events


def test_no_approval_no_writes():
    a=Fixture(approved=False); p=plan()
    with pytest.raises(PermissionError,match="NATIVE_APPROVAL"):
        m.migrate(a,p,m.verify_plan(p))
    assert a.events==["verify_owner_and_before"]
    a=Fixture()
    with pytest.raises(PermissionError,match="APPROVED_SCOPE"):
        m.migrate(a,p,"0"*64)
    assert not a.events


@pytest.mark.parametrize("key,value",[("freeze_or_hold_change",True),("provider_writes",True),
                                      ("runtime_or_mcp_restart_allowed",True),
                                      ("monitoring_restart","jason-runtime.service"),
                                      ("new_system_timers",["unexpected.timer"])])
def test_scope_expansion_denied(key,value):
    p=plan(); p[key]=value
    with pytest.raises(PermissionError):m.verify_plan(p)


def test_monitoring_configuration_requires_original_authority(monkeypatch):
    raw=b'{\n  "schema_version": "1.0",\n  "read_profile": "'+m.PROFILE.encode()+b'",\n  "rollback_read_profile": "'+m.PROFILE.encode()+b'"\n}\n'
    monkeypatch.setattr(m,"PROFILE_SOURCE_SHA",sha256(raw).hexdigest())
    manifest={"complete":True,"revision":m.LKG,"mcp_revision":m.LKG,
              "runtime_revision":m.LKG,"mcp_image_id":m.MCP_IMAGE}
    result=m.monitoring_environment(m.ENV_BEFORE,raw,manifest)
    assert result.startswith(m.ENV_BEFORE)
    assert ("JASON_EXPECTED_MCP_IMAGE_PREFIX="+m.MCP_IMAGE).encode() in result
    assert ("JASON_EXPECTED_PROVIDER_PROFILE="+m.PROFILE).encode() in result
    for bad in ({**manifest,"mcp_image_id":"sha256:"+"0"*64},
                {**manifest,"complete":False}):
        with pytest.raises(PermissionError):m.monitoring_environment(m.ENV_BEFORE,raw,bad)
    with pytest.raises(PermissionError):m.monitoring_environment(m.ENV_BEFORE,raw+b" ",manifest)
    with pytest.raises(PermissionError):m.monitoring_environment(m.ENV_BEFORE+b"x=y\n",raw,manifest)


def test_timer_started_is_not_completion():
    class A:
        def actual_normal_cycle_evidence(self):
            return {"normal_timer_invocation":True,"native_manager_guard":"pass","worker_identity":"al",
                    "pipeline_completed":False}
    with pytest.raises(PermissionError,match="SCHEDULED_ACCEPTANCE_INCOMPLETE"):
        m.verify_scheduled_acceptance(A())


def test_failure_to_persist_before_images_never_calls_mutating_rollback():
    a=Fixture(fail="persist_before_images"); p=plan()
    with pytest.raises(RuntimeError): m.migrate(a,p,m.verify_plan(p))
    assert a.events==["verify_owner_and_before","persist_before_images"]
