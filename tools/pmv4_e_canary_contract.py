#!/usr/bin/env python3
"""Strict read-only contract for existing component controller's E canary.

Source only. Does not install a root adapter, invoke Docker, issue Owner proof
or authorize a production release or retirement.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from tools import independent_component_release as native

CANARY_ID="pmv4-e-canary"
CANARY_PROJECT="jason-pmv4-e-canary"
CANARY_CONTAINER_NAME="jason-pmv4-e-canary-pmv4-e-canary-1"
IMAGE_SOURCE="75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
IMAGE="sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd"
MEMORY_BYTES=134217728
NETWORK="jason-pmv4-e-canary-private"
def mount_source(candidate_sha:str)->str:
    return ("/var/lib/jason/independent-component-release/releases/"
            +candidate_sha+"/config.json")


SCOPE={
    "provider":"none","profile":"","tenant_id":"","scope_id":"",
    "client_id":"","application_id":"",
}


def manifest(*,compose:bytes,config:bytes,freeze_sha256:str,
             candidate_sha:str)->dict[str,Any]:
    result={
        "schema_version":"1.0",
        "release_mode":"owner-signed-independent-compose",
        "repository":"al-teamaot-com/jason",
        "component_id":CANARY_ID,
        "compose_project":CANARY_PROJECT,
        "compose_service":CANARY_ID,
        "candidate_sha":candidate_sha,
        "rollback_sha":native.ZERO,
        "image_digest":IMAGE,
        "compose_sha256":sha256(compose).hexdigest(),
        "config_sha256":sha256(config).hexdigest(),
        "boundary_sha256":"0"*64,
        "scope_sha256":"",
        "freeze_sha256":freeze_sha256,
        "provider_scope":dict(SCOPE),
        "protected_services":list(native.PROTECTED),
        "rollback_mode":"remove-component-only",
    }
    scope={key:result[key] for key in native.SCOPE_FIELDS}
    result["scope_sha256"]=sha256(native.canonical(scope)).hexdigest()
    return result


def deny(code:str)->None:
    raise native.ComponentReleaseDenied("PMV4_E_CANARY_"+code)


def validate_resolved_compose(data:Mapping[str,Any],*,candidate_sha:str)->None:
    """Exact docker compose config projection from reviewed source, no shell."""
    if not isinstance(data,Mapping) or set(data)!={"name","services","networks"}:
        deny("UNEXPECTED_TOPLEVEL")
    if data["name"]!=CANARY_PROJECT or set(data["services"])!={CANARY_ID}:
        deny("PROJECT_OR_SERVICE_CHANGED")
    nets=data["networks"]
    if (not isinstance(nets,dict) or set(nets)!={"isolation"}
        or nets["isolation"].get("name")!=NETWORK
        or nets["isolation"].get("internal") is not True):
        deny("NETWORK_NOT_INTERNAL")
    c=data["services"][CANARY_ID]
    if not isinstance(c,dict) or set(c)!={
        "cap_drop","command","entrypoint","healthcheck","image","mem_limit",
        "labels","networks","pids_limit","pull_policy","read_only","restart",
        "security_opt","user","volumes",
    }:
        deny("SERVICE_EXTRA_CAPABILITY")
    # Compose v2 and v5 differ only in how they serialize a short-syntax
    # bind's implied host-path creation flag. The root controller MUST
    # verify the immutable source file exists before any Docker operation.
    volumes=c.get("volumes")
    if not isinstance(volumes,list) or len(volumes)!=1:
        deny("UNPINNED_CONFIG_BIND")
    volume=volumes[0]
    if not isinstance(volume,dict):
        deny("UNPINNED_CONFIG_BIND")
    binder=volume.get("bind",{})
    if not isinstance(binder,dict) or not (
        binder=={} or (set(binder)=={"create_host_path"}
                        and binder["create_host_path"] is True)
    ):
        deny("UNPINNED_CONFIG_BIND")
    if ({k:v for k,v in volume.items() if k!="bind"}!={
        "type":"bind","source":mount_source(candidate_sha),
        "target":"/canary/config.json","read_only":True,
    }):
        deny("UNPINNED_CONFIG_BIND")
    memory=c.get("mem_limit")
    mem_exact=((type(memory) is int and memory==MEMORY_BYTES)
               or (type(memory) is str and memory==str(MEMORY_BYTES)))
    if (c.get("image")!=IMAGE
        or c.get("read_only") is not True
        or c.get("user")!="1000:1000"
        or c.get("cap_drop")!=["ALL"]
        or c.get("security_opt")!=["no-new-privileges:true"]
        or c.get("labels")!={"com.aot.jason.release_sha":candidate_sha}
        or c.get("networks") not in ({"isolation":None},{"isolation":{}})
        or not mem_exact
        or c.get("pids_limit")!=64
        or c.get("restart")!="no"
        or c.get("pull_policy")!="never"
        or c.get("command") is not None
        or c.get("entrypoint")!=[
            "node","-e","setInterval(() => {}, 30000)"]
        or c.get("healthcheck")!={"test":[
            "CMD","node","-e","process.exit(0)"],
            "timeout":"3s","interval":"10s","retries":3}
        ):
        deny("ISOLATION_OR_PROTECTED_MOUNT_CHANGED")


def validate_exact_image(record:Mapping[str,Any])->None:
    if not isinstance(record,Mapping) or record.get("Id")!=IMAGE:
        deny("IMAGE_NOT_PINNED")
    labels=(record.get("Config") or {}).get("Labels") or {}
    if not isinstance(labels,Mapping) or any(
        labels.get(k)!=v for k,v in {
            "com.aot.jason.component":"pmv4-shadow",
            "com.aot.jason.lifecycle":"preproduction-only",
            "com.aot.jason.production-core":"excluded",
            "com.aot.jason.provider-mutations":"disabled",
            "com.aot.jason.source_revision":IMAGE_SOURCE,
        }.items()
    ):
        deny("IMAGE_SECURITY_LABELS_NOT_PINNED")


def source_only_canary_packet(
    base:Path,*,freeze_sha256:str,candidate_sha:str)->dict[str,Any]:
    compose=(base/"infrastructure/pmv4-e-canary/compose.yaml").read_bytes()
    config=(base/"infrastructure/pmv4-e-canary/config.json").read_bytes()
    m=manifest(compose=compose,config=config,freeze_sha256=freeze_sha256,
               candidate_sha=candidate_sha)
    native.validate_manifest(m)
    native.validate_compose(compose,m)
    scope={key:m[key] for key in native.SCOPE_FIELDS}
    if sha256(native.canonical(scope)).hexdigest()!=m["scope_sha256"]:
        deny("REVIEWED_SCOPE_DIFFERENT")
    return {
        "status":"source_only_providerfree_canary",
        "manifest":m,
        "scope":scope,
        "production_mutations":False,
        "root_installed":False,
        "owner_approval_issued":False,
        "native_controller_production_parity_accepted":False,
    }
