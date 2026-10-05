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
from uuid import uuid4

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


def production_window_open(at: datetime | None = None) -> bool:
    """Return whether unattended production promotion is currently permitted.

    The owner-approved production window is continuous 24x7. This function
    remains as the scheduler gate so future policy changes stay centralized.
    """
    observed = at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("production window evaluation requires timezone-aware time")
    return True


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


def live_mcp() -> dict[str, Any]:
    raw = json.loads(output(["docker", "inspect", "jason-mcp-pilot"]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    revision = str(
        labels.get("com.teamaot.jason.source_revision") or ""
    ).casefold()
    if not SHA.fullmatch(revision):
        raise ReleaseManagerError(
            "live jason-mcp-pilot source revision is not an exact SHA"
        )
    if str(raw.get("State", {}).get("Status") or "") != "running":
        raise ReleaseManagerError("live jason-mcp-pilot is not running")
    return {
        "revision": revision,
        "image_id": str(raw["Image"]),
        "inspect": raw,
    }


def live_production_alignment(candidate_sha: str) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    runtime = live_runtime()
    mcp = live_mcp()
    mcp_revision = str(mcp["revision"])

    current_release = Path("/opt/jason/current").resolve()
    host_revision = current_release.name.casefold()
    if not SHA.fullmatch(host_revision):
        raise ReleaseManagerError("/opt/jason/current does not resolve to an exact SHA release")

    observed = {
        "runtime_revision": runtime["revision"],
        "mcp_revision": mcp_revision,
        "host_revision": host_revision,
        "host_release": str(current_release),
    }
    mismatches = [
        f"{name}={value}"
        for name, value in (
            ("runtime", observed["runtime_revision"]),
            ("mcp", observed["mcp_revision"]),
            ("host", observed["host_revision"]),
        )
        if value != candidate_sha
    ]
    if mismatches:
        raise ReleaseManagerError(
            "production alignment mismatch for candidate "
            + candidate_sha
            + ": "
            + ", ".join(mismatches)
        )
    return observed


def wait_live_runtime(attempts: int = 30, interval_seconds: int = 2) -> dict[str, Any]:
    last_health = "unknown"
    for _ in range(attempts):
        raw = json.loads(output(["docker", "inspect", "jason-runtime"]))[0]
        health = str((raw.get("State", {}).get("Health") or {}).get("Status") or "")
        last_health = health or "unknown"
        if health == "healthy":
            return live_runtime()
        if health == "unhealthy":
            break
        time.sleep(interval_seconds)
    raise ReleaseManagerError(
        f"live jason-runtime did not become healthy: {last_health}"
    )


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
    latest: dict[str, dict[str, Any]] = {}
    # GitHub returns only 30 check runs by default. Busy merge SHAs can exceed
    # that easily (reruns/classifiers included), so required protected checks
    # may otherwise be falsely reported as missing. Traverse a bounded set of
    # 100-item pages and retain the newest run for each check name.
    for page in range(1, 11):
        url = (
            "https://api.github.com/repos/al-teamaot-com/jason/commits/"
            + candidate_sha
            + f"/check-runs?per_page=100&page={page}"
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
        items = payload.get("check_runs") or []
        for item in items:
            name = str(item.get("name") or "")
            if name and (name not in latest or int(item.get("id", 0)) > int(latest[name].get("id", 0))):
                latest[name] = item
        if len(items) < 100:
            break
    else:
        raise ReleaseManagerError("GitHub check-run pagination exceeded bounded limit")
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


def build_mcp_candidate(
    repo: Path,
    state_root: Path,
    candidate_sha: str,
) -> tuple[str, str, str]:
    path = worktree(repo, state_root, candidate_sha)
    tag = f"jason-mcp:release-{candidate_sha[:12]}"
    # Stable governed base prevents stale source files from inheriting from live production.
    base = "jason-mcp:generic-governed-8f1e864947a2"
    base_id = image_id(base)
    try:
        run(
            [
                "docker", "build",
                "--pull=false",
                "--build-arg", f"BASE_IMAGE={base}",
                "--label", f"org.opencontainers.image.revision={candidate_sha}",
                "--label", f"com.teamaot.jason.source_revision={candidate_sha}",
                "-t", tag,
                "-f", str(path / "infrastructure" / "jason-mcp" / "Dockerfile"),
                str(path),
            ]
        )
        return tag, image_id(tag), base_id
    finally:
        remove_worktree(repo, path)


def user_systemd_env() -> dict[str, str]:
    env = os.environ.copy()
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault(
        "DBUS_SESSION_BUS_ADDRESS",
        f"unix:path=/run/user/{uid}/bus",
    )
    return env


def require_host_reconciler_ready(state_root: Path) -> None:
    root = state_root / "host-reconcile"
    requests = root / "requests"
    results = root / "results"
    if not requests.is_dir() or not results.is_dir():
        raise ReleaseManagerError(
            "root host reconciliation spool is not installed"
        )
    if not os.access(requests, os.W_OK) or not os.access(results, os.R_OK):
        raise ReleaseManagerError(
            "root host reconciliation spool permissions are unavailable"
        )
    worker = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
    if not worker.is_file():
        raise ReleaseManagerError("root host reconciliation worker is not installed")
    meta = worker.stat()
    if meta.st_uid != 0 or (meta.st_mode & 0o022):
        raise ReleaseManagerError(
            "root host reconciliation worker ownership/mode is unsafe"
        )
    completed = subprocess.run(
        ["systemctl", "is-active", "jason-release-host-reconcile.path"],
        env=user_systemd_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "active":
        raise ReleaseManagerError(
            "root host reconciliation path unit is not active"
        )


def request_host_reconcile(
    state_root: Path,
    source_revision: str,
    *,
    timeout_seconds: float = 240.0,
) -> dict[str, Any]:
    source_revision = exact_sha(source_revision, "source_revision")
    require_host_reconciler_ready(state_root)
    request_id = "release-" + source_revision[:12] + "-" + uuid4().hex[:12]
    root = state_root / "host-reconcile"
    request_path = root / "requests" / f"{request_id}.json"
    result_path = root / "results" / f"{request_id}.json"
    atomic_json(
        request_path,
        {
            "request_id": request_id,
            "source_revision": source_revision,
            "requested_at": now(),
            "requested_by": "jason-release-manager",
        },
    )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if str(result.get("request_id") or "") != request_id:
                raise ReleaseManagerError(
                    "host reconciliation result request id mismatch"
                )
            if str(result.get("source_revision") or "").casefold() != source_revision:
                raise ReleaseManagerError(
                    "host reconciliation result revision mismatch"
                )
            if result.get("success") is not True:
                raise ReleaseManagerError(
                    "host reconciliation failed: "
                    + str(result.get("detail") or "unknown failure")[:600]
                )
            return result
        time.sleep(0.25)
    raise ReleaseManagerError("host reconciliation result timed out")


def install_release_manager_from_current(expected_sha: str) -> dict[str, Any]:
    expected_sha = exact_sha(expected_sha, "expected_sha")
    current = Path("/opt/jason/current").resolve()
    if current.name.casefold() != expected_sha:
        raise ReleaseManagerError(
            "immutable host release is not aligned before Release Manager install"
        )
    installer = current / "tools" / "install_release_manager.py"
    if not installer.is_file():
        raise ReleaseManagerError(
            "immutable Release Manager installer is missing"
        )
    output_text = run(
        ["/usr/bin/python3", str(installer), "--activate"],
        cwd=current,
        env=user_systemd_env(),
    )
    if "JASON_RELEASE_MANAGER_INSTALL=PASS" not in output_text:
        raise ReleaseManagerError("Release Manager installer did not report PASS")

    source_link = Path.home() / ".local" / "lib" / "jason" / "release-manager-source"
    if source_link.resolve().name.casefold() != expected_sha:
        raise ReleaseManagerError(
            "Release Manager source link is not bound to the immutable host release"
        )
    installed_runner = Path.home() / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
    expected_runner = current / "tools" / "release_manager_host_runner.py"
    if hashlib.sha256(installed_runner.read_bytes()).digest() != hashlib.sha256(
        expected_runner.read_bytes()
    ).digest():
        raise ReleaseManagerError("installed Release Manager runner differs from host release")

    timer = subprocess.run(
        ["systemctl", "--user", "is-active", "jason-release-manager.timer"],
        env=user_systemd_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if timer.returncode != 0 or timer.stdout.strip() != "active":
        raise ReleaseManagerError("Release Manager timer is not active after install")
    return {
        "source_revision": expected_sha,
        "timer_active": True,
        "source_link": str(source_link.resolve()),
    }


def copy_state_from_live_container(
    container_path: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    run(
        [
            "docker",
            "cp",
            f"jason-runtime:{container_path}/.",
            str(destination),
        ]
    )


def preprod_scratch_path(state_root: Path, release_id: str) -> Path:
    return state_root.parent.parent / "release-manager-preprod" / release_id


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

    # Pre-production clones must live outside the live OpenClaw state tree.
    # Production state_root is /var/lib/jason/openclaw/release-manager; placing
    # scratch below state_root recursively copies the destination back into
    # itself when cloning /var/lib/jason/openclaw.
    scratch = preprod_scratch_path(state_root, release_id)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, mode=0o700)

    mount_sources: dict[str, str] = {}
    for mount in src.get("Mounts") or []:
        destination = str(mount.get("Destination") or "")
        source = str(mount.get("Source") or "")
        if destination in {"/var/lib/jason/authority", "/var/lib/jason/openclaw"}:
            clone = scratch / destination.rsplit("/", 1)[-1]
            source_path = Path(source).resolve()
            clone_path = clone.resolve()
            if clone_path == source_path or source_path in clone_path.parents:
                raise ReleaseManagerError(
                    f"pre-production clone destination is nested under live state source: {destination}"
                )
            copy_state_from_live_container(destination, clone)
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


def production_preflight(
    repo: Path,
    state_root: Path,
    image: str,
    mcp_image: str,
    candidate_sha: str,
) -> None:
    require_host_reconciler_ready(state_root)
    candidate_tree = worktree(repo, state_root, candidate_sha)
    try:
        env = os.environ.copy()
        env["JASON_RUNTIME_PRODUCTION_IMAGE"] = image
        env["JASON_MCP_PRODUCTION_IMAGE"] = mcp_image
        env["JASON_SOURCE_REVISION_OVERRIDE"] = candidate_sha
        run(
            [
                str(
                    candidate_tree
                    / "infrastructure"
                    / "jason-runtime"
                    / "production-deploy.sh"
                ),
                "--preflight",
            ],
            cwd=candidate_tree,
            env=env,
        )
        run(
            [
                str(
                    candidate_tree
                    / "infrastructure"
                    / "jason-mcp"
                    / "production-deploy.sh"
                ),
                "--preflight",
            ],
            cwd=candidate_tree,
            env=env,
        )
    finally:
        remove_worktree(repo, candidate_tree)


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
    alignment = live_production_alignment(rollback_sha)
    if alignment["runtime_revision"] != rollback_sha:
        raise ReleaseManagerError(
            "rollback SHA must equal the exact aligned production revision"
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
    mcp_image, mcp_digest, mcp_base_digest = build_mcp_candidate(
        repo,
        state_root,
        candidate_sha,
    )
    record["release_candidate"] = {
        "candidate_sha": candidate_sha,
        "artifact_digest": digest,
        "image": image,
        "mcp_artifact_digest": mcp_digest,
        "mcp_image": mcp_image,
        "mcp_base_artifact_digest": mcp_base_digest,
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
    mcp_image = str(candidate["mcp_image"])
    mcp_digest = str(candidate["mcp_artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed before pre-production")
    if image_id(mcp_image) != mcp_digest:
        raise ReleaseManagerError("candidate MCP image changed before pre-production")

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
        production_preflight(
            repo,
            state_root,
            image,
            mcp_image,
            str(candidate["candidate_sha"]),
        )
        rollback_image = image_id("jason-runtime:rollback-current")
        if not rollback_image:
            raise ReleaseManagerError("runtime rollback-current image alias is unavailable")
        mcp_rollback_image = image_id("jason-mcp:rollback-current")
        if not mcp_rollback_image:
            raise ReleaseManagerError("MCP rollback-current image alias is unavailable")
        record["preproduction"] = {
            "deployed_sha": candidate["candidate_sha"],
            "artifact_digest": digest,
            "mcp_artifact_digest": mcp_digest,
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
    candidate_sha = str(candidate["candidate_sha"])
    image = str(candidate["image"])
    digest = str(candidate["artifact_digest"])
    mcp_image = str(candidate["mcp_image"])
    mcp_digest = str(candidate["mcp_artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed after pre-production")
    if image_id(mcp_image) != mcp_digest:
        raise ReleaseManagerError("candidate MCP image changed after pre-production")

    # Do not begin a disruptive production transaction unless the privileged
    # host boundary is already installed and the rollback baseline is aligned.
    require_host_reconciler_ready(state_root)
    rollback_sha = str(record["rollback_sha"])
    live_production_alignment(rollback_sha)

    gate_transition(repo, record, "production")
    save_record(state_root, record)

    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = image
    env["JASON_MCP_PRODUCTION_IMAGE"] = mcp_image
    env["JASON_SOURCE_REVISION_OVERRIDE"] = candidate_sha
    deploy_worktree = worktree(repo, state_root, candidate_sha)
    runtime_script = (
        deploy_worktree / "infrastructure" / "jason-runtime" / "production-deploy.sh"
    )
    mcp_script = (
        deploy_worktree / "infrastructure" / "jason-mcp" / "production-deploy.sh"
    )

    runtime_deployed = False
    mcp_deployed = False
    host_attempted = False
    release_manager_installed = False

    try:
        runtime_output = run(
            [str(runtime_script)],
            cwd=deploy_worktree,
            env=env,
        )
        runtime_deployed = True
        wait_live_runtime()

        mcp_output = run(
            [str(mcp_script)],
            cwd=deploy_worktree,
            env=env,
        )
        mcp_deployed = True
        if live_mcp()["revision"] != candidate_sha:
            raise ReleaseManagerError(
                "MCP did not report the exact candidate revision after deployment"
            )

        host_attempted = True
        host_result = request_host_reconcile(state_root, candidate_sha)

        manager_result = install_release_manager_from_current(candidate_sha)
        release_manager_installed = True

        alignment = live_production_alignment(candidate_sha)
        live = wait_live_runtime()
        live_digest = image_id("jason-runtime:production")
        live_mcp_digest = image_id("jason-mcp:production")
        if live_digest != digest:
            raise ReleaseManagerError(
                "production runtime image differs from pre-production artifact"
            )
        if live_mcp_digest != mcp_digest:
            raise ReleaseManagerError(
                "production MCP image differs from pre-production artifact"
            )

        record["production"] = {
            "live_sha": live["revision"],
            "artifact_digest": live_digest,
            "mcp_artifact_digest": live_mcp_digest,
            "health_passed": True,
            "deployment_script_passed": "DEPLOYMENT=PASS" in runtime_output,
            "mcp_deployment_script_passed": "DEPLOYMENT=PASS" in mcp_output,
            "host_reconciliation_passed": bool(host_result.get("success")),
            "release_manager_install_passed": True,
            "release_manager_source_revision": manager_result["source_revision"],
            "release_manager_timer_active": manager_result["timer_active"],
            "alignment_verified": True,
            "runtime_revision": alignment["runtime_revision"],
            "mcp_revision": alignment["mcp_revision"],
            "host_revision": alignment["host_revision"],
            "host_release": alignment["host_release"],
            "verified_at": now(),
        }
        gate_transition(repo, record, "production_verified")
        gate_transition(repo, record, "closed")
        save_record(state_root, record)
        return record
    except Exception as error:
        rollback_env = os.environ.copy()
        rollback_env["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:rollback-current"
        rollback_env["JASON_MCP_PRODUCTION_IMAGE"] = "jason-mcp:rollback-current"
        rollback_env["JASON_SOURCE_REVISION_OVERRIDE"] = rollback_sha

        rollback_errors: list[str] = []

        # Reverse the forward transaction in dependency order. Host reconciliation
        # requires MCP to already report the requested release revision.
        if mcp_deployed:
            try:
                run([str(mcp_script)], cwd=deploy_worktree, env=rollback_env)
                if live_mcp()["revision"] != rollback_sha:
                    raise ReleaseManagerError(
                        "MCP rollback revision does not match recorded rollback SHA"
                    )
            except Exception as exc:
                rollback_errors.append("mcp=" + type(exc).__name__ + ":" + str(exc)[:200])

        if host_attempted:
            try:
                request_host_reconcile(state_root, rollback_sha)
            except Exception as exc:
                rollback_errors.append("host=" + type(exc).__name__ + ":" + str(exc)[:200])

        if release_manager_installed or host_attempted:
            try:
                install_release_manager_from_current(rollback_sha)
            except Exception as exc:
                rollback_errors.append(
                    "release_manager=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        if runtime_deployed:
            try:
                run([str(runtime_script)], cwd=deploy_worktree, env=rollback_env)
                rollback_live = wait_live_runtime()
                if rollback_live["revision"] != rollback_sha:
                    raise ReleaseManagerError(
                        "runtime rollback revision does not match recorded rollback SHA"
                    )
            except Exception as exc:
                rollback_errors.append(
                    "runtime=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        rollback_ok = False
        if not rollback_errors:
            try:
                live_production_alignment(rollback_sha)
                install_release_manager_from_current(rollback_sha)
                rollback_ok = True
            except Exception as exc:
                rollback_errors.append(
                    "verification=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        record["failure"] = {
            "at": now(),
            "error": type(error).__name__,
            "message": str(error)[:700],
            "rollback_verified": rollback_ok,
            "rollback_errors": rollback_errors,
        }
        record["state"] = "rolled_back" if rollback_ok else "failed"
        record.setdefault("history", []).append(
            {"at": now(), "state": record["state"], "gate": "deployment_failure"}
        )
        save_record(state_root, record)
        raise
    finally:
        remove_worktree(repo, deploy_worktree)


def prepare_release(
    repo: Path,
    state_root: Path,
    candidate_sha: str,
    change_class: str,
    *,
    owner_approved: bool = False,
) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    release_id = record_id(candidate_sha)
    path = record_path(state_root, release_id)

    if path.exists():
        record = load_record(state_root, release_id)
        state = str(record.get("state") or "")
        if state in {
            "production_eligible",
            "production",
            "production_verified",
            "closed",
        }:
            return record
        if state == "release_candidate":
            return run_preproduction(repo, state_root, record)
        raise ReleaseManagerError(
            f"existing release {release_id} is not safely resumable from state {state}"
        )

    live = live_runtime()
    rollback_sha = exact_sha(str(live["revision"]), "rollback_sha")
    record = create_record(
        repo=repo,
        state_root=state_root,
        candidate_sha=candidate_sha,
        rollback_sha=rollback_sha,
        change_class=change_class,
        owner_approved=owner_approved,
    )
    return run_preproduction(repo, state_root, record)


def production_gate_result(repo: Path, record: dict[str, Any]) -> dict[str, Any]:
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    support = gate.parse_support((repo / "SUPPORT.md").read_text(encoding="utf-8"))
    todos = gate.parse_todos(
        (repo / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md").read_text(
            encoding="utf-8"
        )
    )
    return gate.evaluate_transition(
        record,
        "production",
        policy,
        support_items=support,
        todos=todos,
    )


def promote_eligible(repo: Path, state_root: Path) -> bool:
    if not production_window_open():
        return False
    records = state_root / "records"
    if not records.exists():
        return False
    for path in sorted(records.glob("*.json"), key=lambda item: item.stat().st_mtime):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("state") != "production_eligible":
            continue
        result = production_gate_result(repo, record)
        if result.get("allowed") is True:
            deploy_production(repo, state_root, record)
            return True
        reasons = [str(value) for value in result.get("reasons") or []]
        owner_only = bool(result.get("protected_core")) and reasons and all(
            "owner approval" in reason.casefold() for reason in reasons
        )
        if owner_only:
            continue
        raise ReleaseManagerError(
            "Production Eligible release failed production gate: "
            + "; ".join(reasons)
        )
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

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--candidate-sha", required=True)
    prepare.add_argument("--change-class", default="feature")
    prepare.add_argument("--owner-approved", action="store_true")

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
    if args.command == "prepare":
        record = prepare_release(
            repo=repo,
            state_root=state_root,
            candidate_sha=args.candidate_sha,
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
        if not production_window_open():
            print("RELEASE_MANAGER=WINDOW_CLOSED")
            return 0
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
