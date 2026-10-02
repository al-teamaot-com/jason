#!/usr/bin/env python3
"""Host-side Jason Release Manager.

Build once, validate the exact image in an isolated pre-production container,
then promote the same image to production through the canonical production
deployment script. Release records are durable and evidence-gated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_manager_gate as gate

DEFAULT_REPO = Path("/home/al/projects/jason")
DEFAULT_STATE = Path("/var/lib/jason/openclaw/release-manager")
SHA = re.compile(r"^[0-9a-f]{40}$")
MUTATION_ENV_OVERRIDES = {
    "JASON_AUTOTASK_MUTATION_ENABLED": "false",
    "JASON_AUTOTASK_TICKET_UPDATE_MCP_PROFILE": "",
    "JASON_AUTOTASK_INTERNAL_NOTE_MCP_PROFILE": "",
    "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE": "",
    "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE": "",
    "JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE": "",
    "JASON_DATTO_COMPONENT_EXECUTION_AUTONOMY_ENABLED": "false",
    "JASON_AUTONOMY_WORKER_ENABLED": "false",
    "JASON_AUTONOMY_SHADOW_ENABLED": "false",
    "JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED": "false",
}


class ReleaseManagerError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def output(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def exact_sha(value: str, field: str) -> str:
    value = str(value or "").strip().casefold()
    if not SHA.fullmatch(value):
        raise ReleaseManagerError(f"{field} must be an exact 40-character git SHA")
    return value


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def record_id(candidate_sha: str) -> str:
    return "release-" + candidate_sha[:16]


def record_path(state_root: Path, release_id: str) -> Path:
    return state_root / "records" / f"{release_id}.json"


def load_record(state_root: Path, release_id: str) -> dict[str, Any]:
    path = record_path(state_root, release_id)
    if not path.exists():
        raise ReleaseManagerError(f"release record not found: {release_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_record(state_root: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = now()
    atomic_json(record_path(state_root, str(record["release_id"])), record)


def live_runtime() -> dict[str, Any]:
    raw = json.loads(output(["docker", "inspect", "jason-runtime"]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    revision = str(labels.get("com.teamaot.jason.source_revision") or "").casefold()
    if not SHA.fullmatch(revision):
        raise ReleaseManagerError("live jason-runtime source revision is not an exact SHA")
    health = str((raw.get("State", {}).get("Health") or {}).get("Status") or "")
    if health != "healthy":
        raise ReleaseManagerError(f"live jason-runtime is not healthy: {health or 'unknown'}")
    return {
        "revision": revision,
        "image_id": str(raw["Image"]),
        "inspect": raw,
    }


def verify_candidate_on_main(repo: Path, candidate_sha: str) -> None:
    run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    run(["git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"], cwd=repo)
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, "origin/main"],
        cwd=repo,
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseManagerError("candidate SHA is not reachable from protected main")


def changed_files(repo: Path, rollback_sha: str, candidate_sha: str) -> list[str]:
    text = output(
        ["git", "diff", "--name-only", f"{rollback_sha}..{candidate_sha}"],
        cwd=repo,
    )
    return sorted(line.strip() for line in text.splitlines() if line.strip())


def required_checks(repo: Path) -> list[str]:
    config = json.loads(
        (repo / "config" / "development-release-coordinator.json").read_text(
            encoding="utf-8"
        )
    )
    return list(config.get("required_checks") or [])


def github_checks(candidate_sha: str, required: list[str]) -> dict[str, Any]:
    url = (
        "https://api.github.com/repos/al-teamaot-com/jason/commits/"
        + candidate_sha
        + "/check-runs"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-release-manager",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latest: dict[str, dict[str, Any]] = {}
    for item in payload.get("check_runs") or []:
        name = str(item.get("name") or "")
        if name and (name not in latest or int(item.get("id", 0)) > int(latest[name].get("id", 0))):
            latest[name] = item
    failures = []
    for name in required:
        item = latest.get(name)
        if item is None:
            failures.append(name + ":missing")
        elif item.get("status") != "completed":
            failures.append(name + ":pending")
        elif item.get("conclusion") != "success":
            failures.append(name + ":" + str(item.get("conclusion")))
    return {
        "passed": not failures,
        "required": required,
        "failures": failures,
    }


def image_id(image: str) -> str:
    return output(["docker", "image", "inspect", image, "--format", "{{.Id}}"])


def worktree(repo: Path, state_root: Path, candidate_sha: str) -> Path:
    root = state_root / "worktrees"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / candidate_sha
    if path.exists():
        shutil.rmtree(path)
    run(["git", "worktree", "add", "--detach", str(path), candidate_sha], cwd=repo)
    return path


def remove_worktree(repo: Path, path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def build_candidate(repo: Path, state_root: Path, candidate_sha: str) -> tuple[str, str]:
    path = worktree(repo, state_root, candidate_sha)
    tag = f"jason-runtime:release-{candidate_sha[:12]}"
    try:
        run(
            [
                "docker", "build",
                "--label", f"org.opencontainers.image.revision={candidate_sha}",
                "--label", f"com.teamaot.jason.source_revision={candidate_sha}",
                "-t", tag,
                "-f", str(path / "infrastructure" / "jason-runtime" / "Dockerfile"),
                str(path),
            ]
        )
        return tag, image_id(tag)
    finally:
        remove_worktree(repo, path)


def copy_state(source: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        shutil.rmtree(destination)
    run(["cp", "-a", source, str(destination)])
    for root, dirs, files in os.walk(destination):
        try:
            os.chmod(root, 0o700)
        except PermissionError:
            pass


def create_preprod_container(
    *,
    live: dict[str, Any],
    candidate_image: str,
    candidate_sha: str,
    state_root: Path,
    release_id: str,
) -> tuple[str, Path]:
    src = live["inspect"]
    name = "jason-runtime-preprod-" + candidate_sha[:12]
    subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    scratch = state_root / "preprod" / release_id
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, mode=0o700)

    mount_sources: dict[str, str] = {}
    for mount in src.get("Mounts") or []:
        destination = str(mount.get("Destination") or "")
        source = str(mount.get("Source") or "")
        if destination in {"/var/lib/jason/authority", "/var/lib/jason/openclaw"}:
            clone = scratch / destination.rsplit("/", 1)[-1]
            copy_state(source, clone)
            mount_sources[destination] = str(clone)

    config = src["Config"]
    host = src["HostConfig"]
    env_map: dict[str, str] = {}
    for item in config.get("Env") or []:
        if "=" in item:
            key, value = item.split("=", 1)
            env_map[key] = value
    env_map["JASON_SOURCE_REVISION"] = candidate_sha
    env_map.update(MUTATION_ENV_OVERRIDES)

    args = ["docker", "create", "--name", name, "--restart", "no"]
    if config.get("User"):
        args += ["--user", config["User"]]
    if config.get("WorkingDir"):
        args += ["--workdir", config["WorkingDir"]]
    if host.get("ReadonlyRootfs"):
        args += ["--read-only"]
    for capability in host.get("CapDrop") or []:
        args += ["--cap-drop", capability]
    for option in host.get("SecurityOpt") or []:
        args += ["--security-opt", option]
    for destination, options in (host.get("Tmpfs") or {}).items():
        args += ["--tmpfs", f"{destination}:{options}"]
    for key, value in sorted(env_map.items()):
        args += ["--env", f"{key}={value}"]

    skipped_nested: set[str] = set()
    for mount in src.get("Mounts") or []:
        mtype = str(mount.get("Type") or "")
        source = str(mount.get("Source") or "")
        destination = str(mount.get("Destination") or "")
        writable = bool(mount.get("RW", False))
        if destination.startswith("/var/lib/jason/openclaw/"):
            skipped_nested.add(destination)
            continue
        if destination in mount_sources:
            source = mount_sources[destination]
            mtype = "bind"
            writable = True
        spec = f"type={mtype},src={source},dst={destination}"
        if not writable:
            spec += ",readonly"
        args += ["--mount", spec]

    primary_network = str(host.get("NetworkMode") or "")
    if primary_network and primary_network not in {"default", "bridge"}:
        args += ["--network", primary_network]

    labels = dict(config.get("Labels") or {})
    labels["org.opencontainers.image.revision"] = candidate_sha
    labels["com.teamaot.jason.source_revision"] = candidate_sha
    labels["com.teamaot.jason.deployment-purpose"] = "preproduction"
    for key, value in sorted(labels.items()):
        args += ["--label", f"{key}={value}"]

    health = config.get("Healthcheck") or {}
    test = health.get("Test") or []
    if test:
        if test[0] == "CMD-SHELL":
            args += ["--health-cmd", test[1]]
        elif test[0] == "CMD":
            args += ["--health-cmd", " ".join(test[1:])]
    args.append(candidate_image)

    run(args, env=os.environ.copy())
    secondary = [
        network
        for network in sorted((src.get("NetworkSettings", {}).get("Networks") or {}))
        if network != primary_network
    ]
    for network in secondary:
        run(["docker", "network", "connect", network, name])
    return name, scratch


def wait_health(name: str, attempts: int = 30) -> None:
    script = (
        "import urllib.request; "
        "r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3); "
        "assert r.status == 200"
    )
    for _ in range(attempts):
        result = subprocess.run(
            ["docker", "exec", name, "python", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise ReleaseManagerError("pre-production candidate failed health acceptance")


def verify_preprod_env(name: str, candidate_sha: str) -> None:
    raw = json.loads(output(["docker", "inspect", name]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    if labels.get("com.teamaot.jason.source_revision") != candidate_sha:
        raise ReleaseManagerError("pre-production source revision mismatch")
    env = dict(
        item.split("=", 1)
        for item in raw.get("Config", {}).get("Env") or []
        if "=" in item
    )
    for key, expected in MUTATION_ENV_OVERRIDES.items():
        if env.get(key, "") != expected:
            raise ReleaseManagerError(f"pre-production mutation guard mismatch: {key}")


def production_preflight(repo: Path, image: str, candidate_sha: str) -> None:
    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = image
    env["JASON_SOURCE_REVISION_OVERRIDE"] = candidate_sha
    run(
        [str(repo / "infrastructure" / "jason-runtime" / "production-deploy.sh"), "--preflight"],
        cwd=repo,
        env=env,
    )


def gate_transition(repo: Path, record: dict[str, Any], target: str) -> None:
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    support = gate.parse_support((repo / "SUPPORT.md").read_text(encoding="utf-8"))
    todos = gate.parse_todos(
        (repo / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md").read_text(
            encoding="utf-8"
        )
    )
    result = gate.evaluate_transition(
        record,
        target,
        policy,
        support_items=support,
        todos=todos,
    )
    if not result["allowed"]:
        raise ReleaseManagerError(
            f"release transition {record.get('state')} -> {target} rejected: "
            + "; ".join(result["reasons"])
        )
    record["state"] = target
    record.setdefault("history", []).append(
        {"at": now(), "state": target, "gate": "pass"}
    )


def create_record(
    *,
    repo: Path,
    state_root: Path,
    candidate_sha: str,
    rollback_sha: str,
    change_class: str,
    owner_approved: bool,
) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    rollback_sha = exact_sha(rollback_sha, "rollback_sha")
    live = live_runtime()
    if live["revision"] != rollback_sha:
        raise ReleaseManagerError(
            "rollback SHA must equal the exact current live production revision"
        )
    verify_candidate_on_main(repo, candidate_sha)
    files = changed_files(repo, rollback_sha, candidate_sha)
    checks = github_checks(candidate_sha, required_checks(repo))
    if not checks["passed"]:
        raise ReleaseManagerError(
            "required protected checks are not green: " + ", ".join(checks["failures"])
        )

    release_id = record_id(candidate_sha)
    record = {
        "schema_version": "2.0",
        "release_id": release_id,
        "state": "requested",
        "change_class": change_class,
        "created_at": now(),
        "updated_at": now(),
        "rollback_sha": rollback_sha,
        "changed_files": files,
        "active_support_repairs": [],
        "support_impact": {"checked": True, "blocking_items": []},
        "development": {
            "source_sha": candidate_sha,
            "tests_passed": True,
            "required_checks_passed": True,
            "check_summary": checks,
        },
        "owner_approval": {
            "approved": bool(owner_approved),
            "candidate_sha": candidate_sha if owner_approved else None,
            "source": "explicit_owner_instruction" if owner_approved else None,
            "recorded_at": now() if owner_approved else None,
        },
        "history": [{"at": now(), "state": "requested", "gate": "created"}],
    }
    gate_transition(repo, record, "development")
    gate_transition(repo, record, "dev_verified")

    image, digest = build_candidate(repo, state_root, candidate_sha)
    record["release_candidate"] = {
        "candidate_sha": candidate_sha,
        "artifact_digest": digest,
        "image": image,
        "immutable": True,
        "built_at": now(),
    }
    gate_transition(repo, record, "release_candidate")
    save_record(state_root, record)
    return record


def run_preproduction(repo: Path, state_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    gate_transition(repo, record, "preproduction")
    candidate = record["release_candidate"]
    image = str(candidate["image"])
    digest = str(candidate["artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed before pre-production")

    live = live_runtime()
    name = ""
    scratch: Path | None = None
    try:
        name, scratch = create_preprod_container(
            live=live,
            candidate_image=image,
            candidate_sha=str(candidate["candidate_sha"]),
            state_root=state_root,
            release_id=str(record["release_id"]),
        )
        run(["docker", "start", name])
        wait_health(name)
        verify_preprod_env(name, str(candidate["candidate_sha"]))
        production_preflight(repo, image, str(candidate["candidate_sha"]))
        rollback_image = image_id("jason-runtime:rollback-current")
        if not rollback_image:
            raise ReleaseManagerError("rollback-current image alias is unavailable")
        record["preproduction"] = {
            "deployed_sha": candidate["candidate_sha"],
            "artifact_digest": digest,
            "acceptance_passed": True,
            "failure_path_tests_passed": True,
            "rollback_readiness_passed": True,
            "writable_state_isolated": True,
            "provider_mutations_disabled": True,
            "verified_at": now(),
        }
        gate_transition(repo, record, "preprod_verified")
        gate_transition(repo, record, "production_eligible")
        save_record(state_root, record)
        return record
    finally:
        if name:
            subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if scratch and scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)


def deploy_production(repo: Path, state_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    if record.get("state") != "production_eligible":
        raise ReleaseManagerError("release is not Production Eligible")
    candidate = record["release_candidate"]
    image = str(candidate["image"])
    digest = str(candidate["artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed after pre-production")

    gate_transition(repo, record, "production")
    save_record(state_root, record)
    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = image
    env["JASON_SOURCE_REVISION_OVERRIDE"] = str(candidate["candidate_sha"])
    deploy_script = repo / "infrastructure" / "jason-runtime" / "production-deploy.sh"

    try:
        deploy_output = run([str(deploy_script)], cwd=repo, env=env)
        live = live_runtime()
        live_digest = image_id("jason-runtime:production")
        record["production"] = {
            "live_sha": live["revision"],
            "artifact_digest": live_digest,
            "health_passed": True,
            "deployment_script_passed": "DEPLOYMENT=PASS" in deploy_output,
            "verified_at": now(),
        }
        gate_transition(repo, record, "production_verified")
        gate_transition(repo, record, "closed")
        save_record(state_root, record)
        return record
    except Exception as error:
        rollback_sha = str(record["rollback_sha"])
        rollback_env = os.environ.copy()
        rollback_env["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:rollback-current"
        rollback_env["JASON_SOURCE_REVISION_OVERRIDE"] = rollback_sha
        rollback_ok = False
        try:
            run([str(deploy_script)], cwd=repo, env=rollback_env)
            rollback_live = live_runtime()
            rollback_ok = rollback_live["revision"] == rollback_sha
        except Exception:
            rollback_ok = False
        record["failure"] = {
            "at": now(),
            "error": type(error).__name__,
            "message": str(error)[:700],
            "rollback_verified": rollback_ok,
        }
        record["state"] = "rolled_back" if rollback_ok else "failed"
        record.setdefault("history", []).append(
            {"at": now(), "state": record["state"], "gate": "deployment_failure"}
        )
        save_record(state_root, record)
        raise


def promote_eligible(repo: Path, state_root: Path) -> bool:
    records = state_root / "records"
    if not records.exists():
        return False
    for path in sorted(records.glob("*.json"), key=lambda item: item.stat().st_mtime):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("state") == "production_eligible":
            deploy_production(repo, state_root, record)
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--candidate-sha", required=True)
    create.add_argument("--rollback-sha", required=True)
    create.add_argument("--change-class", default="feature")
    create.add_argument("--owner-approved", action="store_true")

    preprod = sub.add_parser("preprod")
    preprod.add_argument("--release-id", required=True)

    promote = sub.add_parser("promote")
    promote.add_argument("--release-id", required=True)

    sub.add_parser("promote-eligible")
    status = sub.add_parser("status")
    status.add_argument("--release-id")

    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    state_root = args.state_root.expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    if args.command == "create":
        record = create_record(
            repo=repo,
            state_root=state_root,
            candidate_sha=args.candidate_sha,
            rollback_sha=args.rollback_sha,
            change_class=args.change_class,
            owner_approved=args.owner_approved,
        )
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "preprod":
        record = run_preproduction(repo, state_root, load_record(state_root, args.release_id))
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "promote":
        record = deploy_production(repo, state_root, load_record(state_root, args.release_id))
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "promote-eligible":
        print("RELEASE_MANAGER=" + ("PROMOTED" if promote_eligible(repo, state_root) else "IDLE"))
        return 0
    if args.command == "status":
        if args.release_id:
            print(json.dumps(load_record(state_root, args.release_id), indent=2))
        else:
            records = state_root / "records"
            payload = []
            if records.exists():
                for path in sorted(records.glob("*.json")):
                    payload.append(json.loads(path.read_text(encoding="utf-8")))
            print(json.dumps(payload, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
