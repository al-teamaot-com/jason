from copy import deepcopy
from pathlib import Path

import pytest

from tools import no_paid_ai_release_scope as policy
from tools import deploy_live_container as clone


def live(name="jason-runtime"):
    return {
        "Name": "/" + name, "Id": "a"*64, "Image": "sha256:"+"b"*64,
        "Config": {"Env":["JASON_SOURCE_REVISION="+"c"*40,
                           "JASON_HOSTED_CONVERSATION_ENABLED=true",
                           "JASON_HOSTED_SEMANTICS_ENABLED=true",
                           "JASON_OTHER_PROVIDER_PROFILE=unchanged"],
                   "Cmd":["python","-m","jason_runtime.ticket_worker_service"],
                   "Labels":{}, "User":"1000:1000", "WorkingDir":"/app"},
        "HostConfig":{"ReadonlyRootfs":True,"CapDrop":["ALL"],"CapAdd":[],
                      "SecurityOpt":["no-new-privileges:true"],
                      "NetworkMode":"jason-core","PortBindings":{},
                      "Memory":2147483648,"NanoCpus":1000000000,"PidsLimit":256,
                      "Mounts":[{"Type":"bind","Source":"/private/role","Target":p,"ReadOnly":True}
                                for p in sorted(policy.CREDENTIAL_MOUNTS)] + [
                                  {"Type":"bind","Source":"/state","Target":"/var/lib/jason","ReadOnly":False}]},
        "NetworkSettings":{"Networks":{"jason-core":{}}},
        "Mounts":[{"Type":"bind","Source":"/private/role","Destination":p,"RW":False}
                  for p in sorted(policy.CREDENTIAL_MOUNTS)] + [
                    {"Type":"bind","Source":"/state","Destination":"/var/lib/jason","RW":True}],
        "State":{"StartedAt":"2026-11-26T21:00:00Z"},
    }


@pytest.mark.parametrize("name", sorted(policy.TARGETS))
def test_exact_projection_candidate_and_rollback(name):
    before=live(name)
    untouched=deepcopy(before)
    after=policy.project_container(before)
    policy.validate_no_paid_container(after)
    assert before==untouched
    assert {k:v for k,v in after["HostConfig"].items() if k!="Mounts"} == {
        k:v for k,v in before["HostConfig"].items() if k!="Mounts"}
    assert after["HostConfig"]["Mounts"]==before["HostConfig"]["Mounts"][2:]
    assert after["Config"]["Cmd"]==before["Config"]["Cmd"]
    assert after["Mounts"]==before["Mounts"][2:]
    assert policy.environment(after)["JASON_OTHER_PROVIDER_PROFILE"]=="unchanged"
    assert policy.project_container(after)==after
    e=policy.release_evidence(before)
    assert e["production_mutations"] is False
    assert e["rollback_requires_same_no_paid_projection"] is True
    assert "/private/role" not in str(e)
    assert e["removed_credential_destinations"]==sorted(policy.CREDENTIAL_MOUNTS)


def test_first_transition_cannot_use_original_paid_rollback():
    with pytest.raises(policy.NoPaidAIDenied,match="HOSTED_FLAGS"):
        policy.validate_no_paid_container(live())
    before=policy.project_container(live())
    before["Config"]["Env"].append("OPENAI_API_KEY=synthetic")
    with pytest.raises(policy.NoPaidAIDenied,match="RAW_CREDENTIAL"):
        policy.validate_no_paid_container(before)


@pytest.mark.parametrize("dest", ["/run", "/run/jason-secrets",
                                     "/run/jason-secrets/openbao/openai",
                                     "/run/jason-secrets/openbao/openai/role_id/child"])
def test_ancestor_or_foreign_paid_mount_fails_closed(dest):
    obj=live()
    obj["Mounts"].append({"Type":"bind","Source":"/other","Destination":dest,"RW":False})
    with pytest.raises(policy.NoPaidAIDenied,match="MOUNT_SCOPE_INVALID"):
        policy.project_container(obj)


def test_foreign_target_and_writable_credential_bind_denied():
    with pytest.raises(policy.NoPaidAIDenied,match="TARGET_DENIED"):
        policy.project_container(live("unrelated"))
    obj=live();obj["Mounts"][0]["RW"]=True
    with pytest.raises(policy.NoPaidAIDenied,match="MOUNT_SCOPE_INVALID"):
        policy.project_container(obj)


def test_existing_clone_profile_preserves_source_and_refuses_reenable(monkeypatch):
    src=live()
    monkeypatch.setattr(clone,"_inspect",lambda n: src)
    cmd,env,net,raw=clone._build_create_command(
        live="jason-runtime",image="sha256:"+"b"*64,source_revision="c"*40,
        harden=True,enforce_no_paid_ai=True)
    assert raw==src and net==[]
    assert all(env[k]=="false" for k in policy.FLAGS)
    assert not any(p in " ".join(cmd) for p in policy.CREDENTIAL_MOUNTS)
    assert "--mount" in cmd and "dst=/var/lib/jason" in " ".join(cmd)
    with pytest.raises(policy.NoPaidAIDenied,match="ENV_OVERRIDE"):
        clone._build_create_command(live="jason-runtime",image="x",source_revision="c"*40,
            harden=True,enforce_no_paid_ai=True,set_env=(policy.FLAGS[0]+"=true",))


def test_canonical_shared_deployments_require_no_paid_projection():
    root=Path(__file__).resolve().parents[2]
    for name in ("jason-runtime","jason-mcp"):
        assert "--enforce-no-paid-ai" in (root/"infrastructure"/name/"production-deploy.sh").read_text()

def test_hidden_configured_mount_and_legacy_shape_cannot_be_restored():
    obj=policy.project_container(live())
    obj["HostConfig"]["Mounts"].append({
        "Type":"bind","Source":"/other","Target":sorted(policy.CREDENTIAL_MOUNTS)[0],
        "ReadOnly":True})
    with pytest.raises(policy.NoPaidAIDenied,match="CONFIGURED_EFFECTIVE"):
        policy.validate_no_paid_container(obj)
    obj=live();obj["HostConfig"]["Binds"]=["/other:/run/jason-secrets:ro"]
    with pytest.raises(policy.NoPaidAIDenied,match="LEGACY_MOUNT_SHAPE"):
        policy.project_container(obj)
