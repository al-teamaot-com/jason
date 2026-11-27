#!/usr/bin/env python3
"""Real isolated Docker rehearsal for the coordinated scoped-backport profile.

Uses only UUID-labelled disposable containers, no mounts, provider network,
published ports, real app startup, or production names. The prefix is NOT a
production Jason container name, so the existing drift watchdog's production
namespace is neither altered nor exempted. This rehearses rollback mechanics,
not operational/provider acceptance or root installation.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from tools.scoped_backport_coordinated import validate_manifest, SHADOW
from tools.scoped_backport_release import digest
from tools.scoped_backport_docker_rehearsal import docker, image_id, snapshot

PREFIX = "aot-isolated-scoped-rehearsal-"
LABEL = "com.teamaot.jason.coordinated_rehearsal"


def _inspect(name: str, run_id: str) -> dict | None:
    if not name.startswith(PREFIX + run_id + "-"):
        raise RuntimeError("REHEARSAL_NAME_OUT_OF_SCOPE")
    p = docker("inspect", name, allow_fail=True)
    if p.returncode:
        return None
    row = json.loads(p.stdout)[0]
    if row["Config"]["Labels"].get(LABEL) != run_id:
        raise RuntimeError("REHEARSAL_FOREIGN_CONTAINER")
    return row


def _remove(name: str, run_id: str) -> None:
    if _inspect(name, run_id) is not None:
        docker("rm", "-f", name)


def _create(name: str, image: str, run_id: str, *, gateway: bool) -> dict:
    if _inspect(name, run_id) is not None:
        raise RuntimeError("REHEARSAL_NAME_COLLISION")
    runtime, opt, code = ("node", "-e", "setTimeout(()=>{},300000)") if gateway else (
        "python", "-c", "import time;time.sleep(300)")
    docker("run", "-d", "--name", name, "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "32", "--memory", "256m", "--no-healthcheck",
           "--label", LABEL+"="+run_id, "--entrypoint", runtime,
           image, opt, code)
    row = _inspect(name, run_id)
    if (not row or row["Image"] != image or not row["State"]["Running"]
            or row.get("Mounts") or row["HostConfig"]["NetworkMode"] != "none"
            or row["HostConfig"].get("PortBindings")):
        raise RuntimeError("REHEARSAL_ISOLATION_OR_IMAGE_DRIFT")
    return row


def run(manifest: dict) -> dict:
    m = validate_manifest(manifest)
    live = tuple(t["name"] for t in m["targets"]) + tuple(m["protected_services"])
    before = snapshot(live)
    if not all(row["running"] for name,row in before.items() if name != SHADOW):
        raise RuntimeError("REHEARSAL_PRODUCTION_PEER_DOWN")
    # This isolated preproduction peer is not a mandatory production peer.
    # Preserve and verify its observed state without touching it. Production
    # admission independently checks the root-authorized shadow exception.
    for t in m["targets"]:
        if any(image_id(t[k]) != t[k] for k in ("candidate_image", "rollback_image")):
            raise RuntimeError("REHEARSAL_ARTIFACT_DRIFT")
    rid = uuid4().hex[:16]
    names = {t["name"]:PREFIX+rid+"-"+str(i) for i,t in enumerate(m["targets"])}
    originals = {}
    events = []
    def verify_originals():
        for t in m["targets"]:
            n = names[t["name"]]
            row = _inspect(n,rid)
            if not row or row["Id"] != originals[n] or row["Image"] != t["rollback_image"] or not row["State"]["Running"]:
                raise RuntimeError("REHEARSAL_ORIGINAL_IDENTITY_NOT_RESTORED")

    def replace(t, *, omit_candidate=False):
        n=names[t["name"]]; rb=n+"-rollback"
        current=_inspect(n,rid)
        if not current or current["Id"] != originals[n] or _inspect(rb,rid):
            raise RuntimeError("REHEARSAL_PREDECESSOR_DRIFT")
        docker("stop", n); docker("rename",n,rb)
        if not omit_candidate:
            _create(n,t["candidate_image"],rid,gateway=t["name"]=="jason-teams-gateway")
        events.append(("rename_only" if omit_candidate else "replace")+":"+t["name"])

    def restore_all():
        for t in reversed(m["targets"]):
            n=names[t["name"]]; rb=n+"-rollback"
            row=_inspect(n,rid)
            if row and row["Id"]==originals[n]:
                if not row["State"]["Running"]:docker("start",n)
                continue
            previous=_inspect(rb,rid)
            if (not previous or previous["Id"]!=originals[n]
                    or previous["Image"]!=t["rollback_image"]):
                raise RuntimeError("REHEARSAL_RETAINED_ORIGINAL_DRIFT")
            if row:
                if row["Image"]!=t["candidate_image"]:
                    raise RuntimeError("REHEARSAL_UNKNOWN_CANDIDATE")
                _remove(n,rid)
            docker("rename",rb,n);docker("start",n)
            events.append("restore:"+t["name"])
        verify_originals()

    try:
        for t in m["targets"]:
            n=names[t["name"]]
            originals[n]=_create(n,t["rollback_image"],rid,gateway=t["name"]=="jason-teams-gateway")["Id"]
        # Simulate interruption after rename of the last component, before
        # creation of its replacement. This also exercises partial rollout.
        for t in m["targets"][:-1]:replace(t)
        last=m["targets"][-1];replace(last,omit_candidate=True)
        # Real failure in the final candidate image, with no network or host
        # mounts. Never launch its application or call a provider.
        runtime,opt,code=("node","-e","process.exit(17)") if last["name"]=="jason-teams-gateway" else (
            "python","-c","raise SystemExit(17)")
        fail=docker("run","--rm","--network","none","--read-only","--cap-drop","ALL",
                    "--security-opt","no-new-privileges","--no-healthcheck",
                    "--entrypoint",runtime,last["candidate_image"],opt,code,allow_fail=True)
        if fail.returncode!=17:raise RuntimeError("REHEARSAL_INJECTION_FAILED")
        restore_all()
        # Successful entire coordinated transition, followed by exact
        # reverse-order rollback to the original container identities.
        for t in m["targets"]:replace(t)
        for t in m["targets"]:
            row=_inspect(names[t["name"]],rid)
            if not row or row["Image"]!=t["candidate_image"] or not row["State"]["Running"]:
                raise RuntimeError("REHEARSAL_CANDIDATE_READBACK_FAILED")
        restore_all()
        if snapshot(live)!=before:raise RuntimeError("REHEARSAL_PRODUCTION_PEER_CHANGED")
        result={"status":"isolated_coordinated_rollback_rehearsal_pass",
                "manifest_sha256":digest(m),
                "targets":[t["name"] for t in m["targets"]],
                "partial_rollout_interrupted_rename_restored":True,
                "full_rollout_original_container_ids_restored":True,
                "production_snapshot_unchanged":True,"network_enabled":False,
                "provider_writes":False,"production_mutations":False,
                "native_root_release_admitted":False,"events":events,
                "observed_at":datetime.now(timezone.utc).isoformat()}
    finally:
        for n in names.values():
            _remove(n,rid);_remove(n+"-rollback",rid)
        if snapshot(live)!=before:raise RuntimeError("REHEARSAL_FINAL_PRODUCTION_PEER_CHANGED")
    return result
