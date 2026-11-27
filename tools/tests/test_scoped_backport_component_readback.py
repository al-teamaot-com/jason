"""Effective component state is not a waiver of native host convergence."""
from copy import deepcopy
import pytest
from tools import scoped_backport_component_readback as r


def state():
    return {"schema_version":"2.0","status":"verified_component_release",
            "host_revision":"a"*40,"release_id":"release-"+"b"*16,
            "manifest_sha256":"c"*64,"scope_sha256":"d"*64,"freeze_sha256":"e"*64,
            "components":{name:{"revision":str(i+1)*40,"image_id":"sha256:"+str(i+1)*64,
                               "container_id":str(i+4)*64} for i,name in enumerate(r.COMPONENTS)}}


def inspect_rows(s):
    return [{"Name":"/"+name,"Image":row["image_id"],"Id":row["container_id"],
             "Config":{"Labels":{"com.teamaot.jason.source_revision":row["revision"]}},
             "State":{"Running":True,"Status":"running","Health":{"Status":"healthy"}}}
            for name,row in s["components"].items()]


def test_exact_mixed_component_state():
    s=state()
    actual=r.observed(inspect_rows(s))
    assert r.verify(s,actual,host_revision=s["host_revision"],freeze_sha256=s["freeze_sha256"])==s


@pytest.mark.parametrize("bad",["revision","image_id","container_id"])
def test_independent_component_drift_denied(bad):
    s=state();actual=deepcopy(s["components"])
    actual["jason-mcp-pilot"][bad]="sha256:"+"f"*64 if bad=="image_id" else "f"*(40 if bad=="revision" else 64)
    with pytest.raises(r.ComponentReadbackDenied,match="COMPONENT_IDENTITY_DRIFT"):
        r.verify(s,actual,host_revision=s["host_revision"],freeze_sha256=s["freeze_sha256"])


def test_host_or_freeze_change_denied():
    s=state()
    for host,freeze in [("f"*40,s["freeze_sha256"]),(s["host_revision"],"f"*64)]:
        with pytest.raises(r.ComponentReadbackDenied):
            r.verify(s,s["components"],host_revision=host,freeze_sha256=freeze)


@pytest.mark.parametrize("field,value",[("Running",False),("Status","exited"),("Health",{"Status":"unhealthy"})])
def test_no_production_health_waiver(field,value):
    rows=inspect_rows(state());rows[0]["State"][field]=value
    with pytest.raises(r.ComponentReadbackDenied):r.observed(rows)


def test_no_arbitrary_component_or_extra_authority():
    s=state();s["components"]["openbao"]=s["components"].pop("jason-runtime")
    with pytest.raises(r.ComponentReadbackDenied):r.validate(s)
    s=state();s["root_authority"]=True
    with pytest.raises(r.ComponentReadbackDenied):r.validate(s)


def test_native_host_revalidation_does_not_claim_common_revision():
    s=state()
    keys=("host_release","release_manager_source_revision","desired_state_policy_digest",
          "mobile_release_approval_policy_digest","mobile_release_approval_mode","scheduled_control_units")
    legacy={k:"unchanged" for k in keys}
    legacy.update(complete=True,revision=s["host_revision"],host_revision=s["host_revision"],
                  runtime_revision=s["host_revision"],mcp_revision=s["host_revision"])
    current=deepcopy(legacy)
    for name,prefix in (("jason-runtime","runtime"),("jason-mcp-pilot","mcp")):
        current[prefix+"_revision"]=s["components"][name]["revision"]
        current[prefix+"_image_id"]=s["components"][name]["image_id"]
    current["coordinated_readback_sha256"]=r.digest(s)
    r.verify_host_fingerprint(legacy,current,s)
    for field in keys:
        changed=deepcopy(current);changed[field]="foreign"
        with pytest.raises(r.ComponentReadbackDenied,match="HOST_FINGERPRINT_DRIFT"):
            r.verify_host_fingerprint(legacy,changed,s)
