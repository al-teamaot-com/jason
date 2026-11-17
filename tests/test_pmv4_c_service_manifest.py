from __future__ import annotations

from copy import deepcopy
import pytest

from tools import pmv4_c_service_manifest as svc

SOURCE="a"*40
IMAGE="sha256:"+"b"*64

def live_env():
    return {
        "PATH":"/usr/bin",
        "JASON_AUTONOMY_WORKER_ENABLED":"true",
        "JASON_AUTONOMY_WORKER_DB":
            "/var/lib/jason/openclaw/autonomy-operational-work.sqlite3",
        "JASON_AUTOTASK_MUTATION_ENABLED":"true",
        "JASON_AUTONOMY_WORKER_INTERVAL_SECONDS":"60",
        "JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS":"4",
        "JASON_AUTONOMY_OWNED_AUTOTASK_RESOURCE_IDS":"29682930",
        "JASON_HOSTED_SEMANTICS_ENABLED":"true",
        "JASON_HOSTED_CONVERSATION_ENABLED":"true",
        "JASON_DYNAMIC_CONVERSATION_ENABLED":"true",
        "JASON_CONVERSATION_EXPERIENCE_ENABLED":"true",
        "JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE":"autonomous-repair-v1",
        "JASON_PM_V2_CONTROL_PROFILE":"owner-teams-v1",
        "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE":"owner-procurement-v1",
        "JASON_PROCUREMENT_WEB_READ_PROFILE":"aot-procurement-web-v1",
        "JASON_DNSFILTER_ENABLED":"true",
        "JASON_DARKWEBID_ENABLED":"true",
        "JASON_DNSFILTER_MCP_ENABLED":"true",
        "JASON_DNSFILTER_MCP_MUTATION_ENABLED":"true",
        "JASON_BACKUP_NET_ENABLED":"true",
        "JASON_BACKUP_NET_ACCESS_PROFILE":"full_access",
        "JASON_QUICKBOOKS_READ_PROFILE":"quickbooks-production-read-v1",
        "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH":
            "/run/jason-secrets/openbao/quickbooks-production/role_id",
        "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH":
            "/run/jason-secrets/openbao/quickbooks-production/secret_id",
        "JASON_TEAMS_PROACTIVE_TOKEN_FILE":
            "/run/jason-secrets/teams-proactive-gateway/token",
    }

def test_manifest_is_non_http_exact_bounded_worker():
    m=svc.build_manifest(live_env(),source_sha=SOURCE,image_digest=IMAGE)
    assert m["component"]=="pmv4-ticket-core"
    assert m["command"]==list(svc.COMMAND)
    assert m["user"]=="1000:1000"
    assert m["network_mode"]=="jason-core"
    assert m["read_only_rootfs"] is True
    assert m["privileged"] is False
    assert m["cap_drop"]==["ALL"]
    assert m["cap_add"]==[]
    assert m["port_bindings"]=={}
    assert m["environment"]["JASON_TICKET_WORKER_HOSTING"]=="external"
    assert m["environment"]["JASON_SOURCE_REVISION"]==SOURCE
    assert m["labels"]["com.aot.jason.lifecycle"]=="production-candidate"
    assert m["environment"]["JASON_HOSTED_CONVERSATION_ENABLED"]=="false"
    assert m["environment"]["JASON_HOSTED_SEMANTICS_ENABLED"]=="true"
    for key in (
        "JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE",
        "JASON_PM_V2_CONTROL_PROFILE",
        "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE",
        "JASON_PROCUREMENT_WEB_READ_PROFILE",
        "JASON_M365_GROUP_ADMIN_PROFILE",
    ):
        assert m["environment"][key]==""
    assert m["owner_authorization_issued"] is False
    assert m["production_mutations"] is False
    assert len(m["manifest_sha256"])==64
    assert len(m["environment_sha256"])==64

def test_non_jason_and_raw_secret_env_never_copied():
    source=live_env()
    source["HOME"]="/root"
    source["SOME_OTHER"]="value"
    env=svc.reviewed_worker_environment(source)
    assert "HOME" not in env and "SOME_OTHER" not in env
    source["JASON_FAKE_API_KEY"]="raw-secret"
    with pytest.raises(svc.ServiceManifestDenied,match="RAW_SECRET_ENV_DENIED"):
        svc.reviewed_worker_environment(source)
    source.pop("JASON_FAKE_API_KEY")
    source["JASON_FAKE_SECRET_PATH"]="/run/secret"
    assert svc.reviewed_worker_environment(source)["JASON_FAKE_SECRET_PATH"]=="/run/secret"

@pytest.mark.parametrize("key,value",[
    ("JASON_AUTONOMY_WORKER_ENABLED","false"),
    ("JASON_AUTONOMY_WORKER_DB","/tmp/other.sqlite3"),
    ("JASON_AUTOTASK_MUTATION_ENABLED","false"),
])
def test_live_baseline_or_ticket_write_parity_must_match(key,value):
    source=live_env();source[key]=value
    with pytest.raises(svc.ServiceManifestDenied,match="C_SERVICE_"):
        svc.build_manifest(source,source_sha=SOURCE,image_digest=IMAGE)

def test_effective_inspect_must_match_every_security_boundary():
    m=svc.build_manifest(live_env(),source_sha=SOURCE,image_digest=IMAGE)
    inspect={
        "Name":"/jason-pmv4-ticket-core",
        "Image":IMAGE,
        "State":{"Running":True,"Health":{"Status":"healthy"}},
        "Config":{
            "User":"1000:1000",
            "Cmd":list(svc.COMMAND),
            "Env":[f"{k}={v}" for k,v in m["environment"].items()],
            "Labels":dict(m["labels"]),
            "ExposedPorts":{},
            "Healthcheck":{
                "Test":list(m["healthcheck"]["test"]),
                "Interval":m["healthcheck"]["interval_ns"],
                "Timeout":m["healthcheck"]["timeout_ns"],
                "Retries":m["healthcheck"]["retries"],
                "StartPeriod":m["healthcheck"]["start_period_ns"],
            },
        },
        "HostConfig":{
            "NetworkMode":"jason-core",
            "ReadonlyRootfs":True,
            "Privileged":False,
            "CapDrop":["ALL"],
            "CapAdd":[],
            "SecurityOpt":["no-new-privileges:true"],
            "RestartPolicy":{"Name":"unless-stopped"},
            "Memory":svc.MEMORY_BYTES,
            "NanoCpus":svc.NANO_CPUS,
            "PidsLimit":svc.PIDS_LIMIT,
            "PortBindings":{},
        },
        "Mounts":[dict(x) for x in m["mounts"]],
    }
    result=svc.validate_effective_inspect(inspect,m)
    assert result["status"]=="effective_ticket_core_security_verified"

    mutations=[
        lambda x:x["HostConfig"].update(Privileged=True),
        lambda x:x["HostConfig"].update(ReadonlyRootfs=False),
        lambda x:x["HostConfig"].update(NetworkMode="bridge"),
        lambda x:x["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
        lambda x:x["HostConfig"].update(PortBindings={"8080/tcp":[{}]}),
        lambda x:x["Config"].update(User="0:0"),
        lambda x:x["Config"].update(Cmd=["sleep","infinity"]),
        lambda x:x["State"]["Health"].update(Status="unhealthy"),
        lambda x:x["Mounts"].append({
            "Source":"/var/run/docker.sock",
            "Destination":"/var/run/docker.sock",
            "RW":False,"Type":"bind"}),
    ]
    for mutate in mutations:
        candidate=deepcopy(inspect)
        mutate(candidate)
        with pytest.raises(svc.ServiceManifestDenied,match="C_SERVICE_"):
            svc.validate_effective_inspect(candidate,m)
