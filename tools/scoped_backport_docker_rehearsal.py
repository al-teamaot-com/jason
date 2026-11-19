#!/usr/bin/env python3
"""Bounded isolated Docker rehearsal for EXACT immutable scoped-backport images.

No production name, network, volumes, credentials, sockets, host state or ports
may be changed. All ephemeral containers are newly generated UUID-namespaced
objects. They are deleted after real Docker revert tests. This does NOT prove
the native production release manager is installed or authorized.
"""
from __future__ import annotations
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from tools.scoped_backport_release import validate_manifest, PROTECTED

LIVE = ("jason-runtime", "jason-mcp-pilot") + PROTECTED
PREFIX = "jason-scoped-backport-rehearsal-"


def docker(*args, allow_fail=False, timeout=40):
    result = subprocess.run(("docker",) + args, capture_output=True,
                            text=True, check=False, timeout=timeout)
    if result.returncode != 0 and not allow_fail:
        raise RuntimeError("REHEARSAL_DOCKER_DENIED:" + " ".join(args[:2]))
    return result


def image_id(image):
    data = json.loads(docker("image", "inspect", image).stdout)
    if len(data) != 1:
        raise RuntimeError("REHEARSAL_IMAGE_CARDINALITY")
    return data[0]["Id"]


def snapshot(names):
    items = json.loads(docker("inspect", *names).stdout)
    if len(items) != len(names):
        raise RuntimeError("REHEARSAL_CONTAINER_MISSING")
    return {i["Name"].lstrip("/"): {
        "id": i["Id"], "image": i["Image"],
        "started_at": i["State"]["StartedAt"],
        "running": bool(i["State"]["Running"]),
    } for i in items}


def create(name, image, run_id):
    if docker("inspect", name, allow_fail=True).returncode == 0:
        raise RuntimeError("REHEARSAL_NAME_COLLISION")
    docker("run", "-d", "--name", name, "--network", "none",
           "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--pids-limit", "32",
           "--memory", "256m",
           "--label", "com.teamaot.jason.scoped_rehearsal=" + run_id,
           "--entrypoint", "python", image,
           "-c", "import time;time.sleep(150)")
    if not snapshot((name,))[name]["running"]:
        raise RuntimeError("REHEARSAL_EPHEMERAL_CONTAINER_NOT_RUNNING")


def destroy(name, run_id):
    p = docker("inspect", name, allow_fail=True)
    if p.returncode:
        return
    meta = json.loads(p.stdout)[0]
    if (meta.get("Config", {}).get("Labels", {}).get(
            "com.teamaot.jason.scoped_rehearsal") != run_id):
        raise RuntimeError("REHEARSAL_FOREIGN_CONTAINER_NOT_REMOVED")
    docker("rm", "-f", name)


def run(manifest):
    m = validate_manifest(manifest)
    before = snapshot(LIVE)
    if any(not v["running"] for v in before.values()):
        raise RuntimeError("REHEARSAL_PROTECTED_CONTAINER_DOWN")
    for field in ("runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
                  "rollback_mcp_image_id"):
        if image_id(m[field]) != m[field]:
            raise RuntimeError("REHEARSAL_IMAGE_ID_DRIFT_" + field)
    run_id = uuid4().hex[:12]
    names = [PREFIX + role + "-" + run_id for role in ("runtime", "mcp")]
    rb_names = [name + "-rollback" for name in names]
    for name in names + rb_names:
        if docker("inspect", name, allow_fail=True).returncode == 0:
            raise RuntimeError("REHEARSAL_COLLISION")
    first_failure_recovered = False
    successful_pair_recovered = False
    try:
        # Phase A: first candidate replaces a baseline copy; second deploy
        # intentionally fails. The first must be restored from its retained
        # rollback image without ever touching production.
        create(names[0], m["rollback_runtime_image_id"], run_id)
        create(names[1], m["rollback_mcp_image_id"], run_id)
        docker("stop", names[0])
        docker("rename", names[0], rb_names[0])
        create(names[0], m["runtime_image_id"], run_id)
        if snapshot((names[0],))[names[0]]["image"] != m["runtime_image_id"]:
            raise RuntimeError("REHEARSAL_RUNTIME_CANDIDATE_DRIFT")
        injected = docker("run", "--rm", "--network", "none", "--read-only",
                          "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                          "--entrypoint", "python", m["mcp_image_id"],
                          "-c", "raise SystemExit(17)", allow_fail=True)
        if injected.returncode != 17:
            raise RuntimeError("REHEARSAL_FAILURE_INJECTION_UNEXPECTED")
        destroy(names[0], run_id)
        docker("rename", rb_names[0], names[0])
        docker("start", names[0])
        result = snapshot(names)
        if (result[names[0]]["image"] != m["rollback_runtime_image_id"]
                or result[names[1]]["image"] != m["rollback_mcp_image_id"]
                or not all(item["running"] for item in result.values())):
            raise RuntimeError("REHEARSAL_ROLLBACK_NOT_VERIFIED")
        first_failure_recovered = True
        # Phase B: candidate pair both replace baseline copies, and both
        # revert to exact retained baseline image IDs (success-path rollback).
        for name in names:
            docker("stop", name)
            docker("rename", name, name + "-rollback")
        create(names[0], m["runtime_image_id"], run_id)
        create(names[1], m["mcp_image_id"], run_id)
        result = snapshot(names)
        if (result[names[0]]["image"] != m["runtime_image_id"]
                or result[names[1]]["image"] != m["mcp_image_id"]):
            raise RuntimeError("REHEARSAL_PAIR_CANDIDATE_DRIFT")
        for name in reversed(names):
            destroy(name, run_id)
            docker("rename", name + "-rollback", name)
            docker("start", name)
        result = snapshot(names)
        if (result[names[0]]["image"] != m["rollback_runtime_image_id"]
                or result[names[1]]["image"] != m["rollback_mcp_image_id"]
                or not all(item["running"] for item in result.values())):
            raise RuntimeError("REHEARSAL_PAIR_RESTORE_FAILED")
        successful_pair_recovered = True
        if snapshot(LIVE) != before:
            raise RuntimeError("REHEARSAL_PRODUCTION_SNAPSHOT_CHANGED")
        return {
            "schema_version": "1.0",
            "status": "isolated_docker_rollback_rehearsal_pass",
            "candidate_sha": m["candidate_sha"],
            "rollback_sha": m["rollback_sha"],
            "candidate_images": [m["runtime_image_id"], m["mcp_image_id"]],
            "rollback_images": [m["rollback_runtime_image_id"],
                                m["rollback_mcp_image_id"]],
            "injected_second_component_failure_recovered": first_failure_recovered,
            "pair_success_path_revert_verified": successful_pair_recovered,
            "protected_container_snapshot_unchanged": True,
            "network_enabled": False,
            "provider_writes": False,
            "production_mutations": False,
            "native_release_manager_transaction_verified": False,
            "production_deployed": False,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        for name in names + rb_names:
            destroy(name, run_id)
        if snapshot(LIVE) != before:
            raise RuntimeError("REHEARSAL_FINAL_PROTECTED_SNAPSHOT_CHANGED")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-isolated-docker-rehearsal", action="store_true")
    args = p.parse_args()
    if not args.run_isolated_docker_rehearsal:
        p.error("explicit --run-isolated-docker-rehearsal is required")
    if args.output.exists() or args.output.is_symlink():
        p.error("output receipt already exists; never overwrite")
    if (not args.output.is_absolute() or
            not str(args.output).startswith("/home/al/.local/share/jason/")):
        p.error("output must be in private Jason engineering evidence")
    manifest = json.loads(args.manifest.read_text())
    evidence = run(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(evidence, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
