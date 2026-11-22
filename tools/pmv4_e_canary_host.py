#!/usr/bin/env python3
"""Source-only companion callbacks for existing protected component controller."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import time

from tools.independent_component_release import (
    ComponentReleaseDenied,validate_manifest,validate_compose,trusted_file,
)
from tools.independent_component_host_adapter import IndependentComponentHost
from tools import pmv4_e_canary_contract as contract

TRUSTED=Path("/opt/jason/independent-component-release/trusted/tools/pmv4_e_canary_host.py")
ROOT=Path("/var/lib/jason/independent-component-release")
BUNDLE=ROOT/"releases"
PRIVATE_NET=contract.NETWORK


def require(ok,code):
    if not ok:raise ComponentReleaseDenied("PMV4_E_CANARY_"+code)


class PinnedCanaryHost:
    def __init__(self,*,production=True,legacy=None):
        if production:
            require(os.geteuid()==0 and Path(__file__).resolve()==TRUSTED
                    and TRUSTED.is_file() and not TRUSTED.is_symlink(),
                    "ROOT_SOURCE_NOT_INSTALLED")
            s=TRUSTED.lstat()
            require(s.st_uid==0 and s.st_gid==0
                    and stat.S_IMODE(s.st_mode)==0o444,
                    "ROOT_SOURCE_NOT_INSTALLED")
            require(legacy is None,"PRODUCTION_CUSTOM_HOST_DENIED")
        self.production=production
        self.legacy=legacy or IndependentComponentHost(production=True)

    def host_transaction(self):return self.legacy.host_transaction()
    def freeze_transaction(self,sha):return self.legacy.freeze_transaction(sha)
    def protected(self):return self.legacy.protected()
    def source_and_ci(self,sha):return self.legacy.source_and_ci(sha)

    def image(self,digest,sha):
        if (digest!=contract.IMAGE or not isinstance(sha,str)
            or len(sha)!=40
            or any(c not in "0123456789abcdef" for c in sha)):
            return False
        try:
            if self.production:
                m=json.loads(trusted_file(
                    BUNDLE/sha/"manifest.json",production=True))
                if (m.get("candidate_sha")!=sha
                    or m.get("component_id")!=contract.CANARY_ID
                    or m.get("image_digest")!=contract.IMAGE
                    or m.get("provider_scope")!=contract.SCOPE):
                    return False
            raw=self.legacy._run(["/usr/bin/docker","image","inspect",digest])
            inspected=json.loads(raw)
            require(len(inspected)==1,"OCI_INSPECT_NOT_SINGLE")
            contract.validate_exact_image(inspected[0])
            return True
        except (OSError,ValueError,TypeError,ComponentReleaseDenied):
            return False

    def _compose(self,bundle,manifest,operation):
        validate_manifest(manifest)
        require(manifest.get("component_id")==contract.CANARY_ID
                and manifest.get("compose_project")==contract.CANARY_PROJECT
                and manifest.get("compose_service")==contract.CANARY_ID
                and manifest.get("image_digest")==contract.IMAGE
                and manifest.get("provider_scope")==contract.SCOPE
                and manifest.get("rollback_sha")=="0"*40,
                "NOT_REVIEWED_CANARY")
        require(not self.production or Path(bundle)==BUNDLE/manifest["candidate_sha"],
                "PRODUCTION_BUNDLE_NOT_FIXED")
        raw=trusted_file(Path(bundle)/"compose.yaml",production=self.production)
        validate_compose(raw,manifest)
        env={"PATH":"/usr/bin:/bin",
             "JASON_PMV4_E_CONFIG":str(Path(bundle)/"config.json"),
             "JASON_PMV4_E_SOURCE":manifest["candidate_sha"]}
        cmd=["/usr/bin/docker","compose","--project-name",contract.CANARY_PROJECT,
             "--file",str(Path(bundle)/"compose.yaml")]
        parsed=json.loads(self.legacy._run(cmd+["config","--format","json"],env=env))
        contract.validate_resolved_compose(
            parsed,candidate_sha=manifest["candidate_sha"])
        if operation is not None:
            self.legacy._run(cmd+operation+[contract.CANARY_ID],env=env,timeout=120)

    def activate(self,bundle,manifest):
        self._compose(bundle,manifest,[
            "up","--detach","--no-deps","--no-build",
            "--pull","never","--force-recreate"])

    def restore(self,previous,manifest):
        require(previous is None,"PRIOR_RELEASE_NOT_EMPTY")
        self._compose(BUNDLE/manifest["candidate_sha"],manifest,[
            "rm","--force","--stop"])

    def observe(self,project):
        require(project==contract.CANARY_PROJECT,"PROJECT_UNREVIEWED")
        raw=self.legacy._run(["/usr/bin/docker","ps","-a","--filter",
                              "label=com.docker.compose.project="+project,
                              "--format","{{.ID}}"])
        ids=[x for x in raw.splitlines() if x.strip()]
        if not ids:return None
        require(len(ids)==1,"AMBIGUOUS_PROJECT")
        deadline=time.monotonic()+35
        while True:
            objects=json.loads(self.legacy._run(
                ["/usr/bin/docker","inspect",ids[0]]))
            require(isinstance(objects,list) and len(objects)==1,
                    "DOCKER_OBSERVATION_AMBIGUOUS")
            item=objects[0]
            state=item.get("State") or {}
            status=(state.get("Health") or {}).get("Status")
            if status=="healthy":
                break
            require(state.get("Running") is True
                    and status=="starting"
                    and time.monotonic()<deadline,
                    "ISOLATED_CONTAINER_STARTUP_OR_HEALTH_DENIED")
            time.sleep(1)
        state=item.get("State") or {}
        host=item.get("HostConfig") or {}
        labels=(item.get("Config") or {}).get("Labels") or {}
        mounts=item.get("Mounts") or []
        networks=(item.get("NetworkSettings") or {}).get("Networks") or {}
        source_sha=labels.get("com.aot.jason.release_sha")
        require(isinstance(source_sha,str) and len(source_sha)==40
                and all(c in "0123456789abcdef" for c in source_sha),
                "SOURCE_RELEASE_LABEL_NOT_SHA")
        require(labels.get("com.docker.compose.project")==project
                and labels.get("com.docker.compose.service")==contract.CANARY_ID
                and item.get("Image")==contract.IMAGE
                and host.get("Memory")==contract.MEMORY_BYTES
                and host.get("PidsLimit")==64
                and host.get("Privileged") is False
                and host.get("ReadonlyRootfs") is True
                and (item.get("Config") or {}).get("User")=="1000:1000"
                and len(mounts)==1 and mounts[0].get("RW") is False
                and mounts[0].get("Destination")=="/canary/config.json"
                and mounts[0].get("Source")==contract.mount_source(source_sha)
                and set(networks)=={PRIVATE_NET}
                and state.get("Running") is True
                and (state.get("Health") or {}).get("Status")=="healthy",
                "ISOLATED_CONTAINER_NOT_ACCEPTED")
        network_rows=json.loads(self.legacy._run([
            "/usr/bin/docker","network","inspect",PRIVATE_NET]))
        require(isinstance(network_rows,list) and len(network_rows)==1,
                "NETWORK_AMBIGUOUS")
        network=network_rows[0]
        require(
            network.get("Name")==PRIVATE_NET
            and network.get("Internal") is True
            and network.get("Driver")=="bridge"
            and network.get("Attachable") is False
            and set(network.get("Containers") or {})=={item.get("Id")},
            "PRIVATE_NETWORK_EGRESS_OR_PEER_NOT_ACCEPTED")
        require(
            not host.get("PortBindings")
            and host.get("CapDrop")==["ALL"]
            and "no-new-privileges:true" in (host.get("SecurityOpt") or [])
            and host.get("NetworkMode")==PRIVATE_NET,
            "EFFECTIVE_DOCKER_SECURITY_NOT_ACCEPTED")
        require(self.image(contract.IMAGE,source_sha),
                "REUSED_IMAGE_PROVENANCE_UNVERIFIED")
        return source_sha

    def verify_component(self,bundle,manifest):
        if bundle is None:return self.observe(contract.CANARY_PROJECT) is None
        end=time.monotonic()+35
        while True:
            try:
                return self.observe(contract.CANARY_PROJECT)==manifest["candidate_sha"]
            except ComponentReleaseDenied as exc:
                if (str(exc)!="PMV4_E_CANARY_ISOLATED_CONTAINER_NOT_ACCEPTED"
                    or time.monotonic()>=end):
                    raise
                time.sleep(1)
