#!/usr/bin/env python3
"""Host-side executor for J-CHANGE-002 autonomous repair deployments.

The Jason runtime never receives Docker or host-shell authority. It writes an
exact governed request into a host bind. This runner independently verifies the
request, current production revision, merged PR, protected checks, J-CHANGE-002
eligibility, and rollback target before building and deploying an exact commit.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_REPO = Path("/home/al/projects/jason")
DEFAULT_SPOOL = Path("/var/lib/jason/openclaw/autonomous-repair")
LIVE_CONTAINER = "jason-runtime"
PROFILE = "autonomous-repair-v1"


class RepairRunnerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture: bool = False,
) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=dict(env) if env is not None else None,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RepairRunnerError(
            "COMMAND_FAILED",
            f"command failed ({args[0]}): {stderr[:500]}",
        )
    return (completed.stdout or "").strip()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("x", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _load_gate(repo: Path):
    path = repo / "tools" / "autonomous_repair_release_gate.py"
    spec = importlib.util.spec_from_file_location("jason_autonomous_repair_release_gate", path)
    if spec is None or spec.loader is None:
        raise RepairRunnerError("GATE_LOAD_FAILED", "repair release gate could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _canonical_request(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "schema_version",
        "capability",
        "provider",
        "principal_id",
        "organization_id",
        "execution_id",
        "correlation_id",
        "candidate_sha",
        "rollback_sha",
        "support_item",
        "pr_number",
        "post_deploy_verification",
        "request_id",
        "request_fingerprint",
    )
    missing = [key for key in required if not str(raw.get(key) or "").strip()]
    if missing:
        raise RepairRunnerError(
            "REQUEST_INVALID",
            "repair request fields missing: " + ", ".join(sorted(missing)),
        )
    if raw.get("schema_version") != "1.0":
        raise RepairRunnerError("REQUEST_INVALID", "unsupported repair request schema")
    if raw.get("capability") != "deployment.repair.apply":
        raise RepairRunnerError("REQUEST_INVALID", "unexpected repair capability")
    if raw.get("provider") != "jason_host_repair_runner":
        raise RepairRunnerError("REQUEST_INVALID", "unexpected repair provider")
    if raw.get("principal_id") != "jason-autonomy-worker":
        raise RepairRunnerError("REQUEST_INVALID", "repair request principal is not autonomous workload")
    if raw.get("organization_id") != "aot":
        raise RepairRunnerError("REQUEST_INVALID", "repair request organization mismatch")

    material = {
        key: raw[key]
        for key in (
            "capability",
            "provider",
            "principal_id",
            "organization_id",
            "candidate_sha",
            "rollback_sha",
            "support_item",
            "pr_number",
            "post_deploy_verification",
        )
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if raw.get("request_id") != fingerprint or raw.get("request_fingerprint") != fingerprint:
        raise RepairRunnerError("REQUEST_FINGERPRINT_MISMATCH", "repair request fingerprint mismatch")
    return dict(raw)


def _live_revision() -> str:
    value = _run(
        [
            "docker",
            "inspect",
            LIVE_CONTAINER,
            "--format",
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ],
        capture=True,
    ).strip().casefold()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RepairRunnerError(
            "LIVE_REVISION_UNVERIFIED",
            "live Jason runtime source revision is not an exact SHA",
        )
    return value


def _live_health() -> str:
    return _run(
        [
            "docker",
            "inspect",
            LIVE_CONTAINER,
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        ],
        capture=True,
    ).strip().casefold()


def _wait_live_health(*, attempts: int = 30, interval_seconds: float = 1.0) -> str:
    attempts = max(1, int(attempts))
    for attempt in range(1, attempts + 1):
        health = _live_health()
        if health == "healthy":
            return health
        if attempt < attempts:
            time.sleep(max(0.0, float(interval_seconds)))
    raise RepairRunnerError(
        "PRODUCTION_NOT_HEALTHY",
        "live Jason runtime did not become healthy within the bounded startup window",
    )


def _verify_git(repo: Path, candidate: str) -> None:
    _run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    _run(["git", "cat-file", "-e", f"{candidate}^{{commit}}"], cwd=repo)
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, "origin/main"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise RepairRunnerError(
            "CANDIDATE_NOT_ON_MAIN",
            "repair candidate is not reachable from current protected main",
        )


def _independent_classification(
    *,
    repo: Path,
    request: Mapping[str, Any],
    live_revision: str,
) -> dict[str, Any]:
    gate = _load_gate(repo)
    policy = gate.load_json(repo / "config" / "autonomous-repair-release-policy.json")
    if not policy.get("automatic_production_execution_enabled", False):
        raise RepairRunnerError(
            "AUTONOMOUS_EXECUTION_DISABLED",
            "autonomous repair production execution is not enabled by policy",
        )

    api = gate.Api(
        os.environ.get("GITHUB_REPOSITORY", "al-teamaot-com/jason"),
        os.environ.get("GITHUB_TOKEN", ""),
    )
    pr_number = int(request["pr_number"])
    pr = api.request(f"/pulls/{pr_number}")
    candidate = str(request["candidate_sha"])
    if str(pr.get("merge_commit_sha") or "").casefold() != candidate:
        raise RepairRunnerError(
            "PR_CANDIDATE_MISMATCH",
            "repair request candidate does not match merged PR commit",
        )
    if not pr.get("merged_at"):
        raise RepairRunnerError("PR_NOT_MERGED", "repair PR is not merged")

    commit = api.request(f"/commits/{candidate}")
    parents = list(commit.get("parents") or [])
    if len(parents) < 2:
        raise RepairRunnerError(
            "REPAIR_MERGE_SHAPE_INVALID",
            "autonomous repair candidate must be a merge commit with a production-side parent",
        )
    production_parent = str((parents[0] or {}).get("sha") or "").casefold()
    if production_parent != live_revision:
        raise RepairRunnerError(
            "UNRELATED_MAIN_CHANGES_PRESENT",
            "repair merge parent does not equal live production; autonomous promotion would bundle unrelated main changes",
        )

    files = api.paged(f"/pulls/{pr_number}/files")
    checks_payload = api.request(f"/commits/{candidate}/check-runs")
    main = api.request("/branches/main")
    main_sha = str(main["commit"]["sha"])
    compare = api.request(f"/compare/{candidate}...{main_sha}")
    merge_is_on_main = compare.get("status") in {"ahead", "identical"} or candidate == main_sha
    support_items = gate.parse_open_support(
        (repo / "SUPPORT.md").read_text(encoding="utf-8")
    )
    production_state = {
        "production": {
            "status": "aligned_and_healthy",
            "observed_at": _now(),
            "revision": live_revision,
        }
    }
    result = gate.classify(
        pr=pr,
        files=files,
        check_runs=list(checks_payload.get("check_runs", [])),
        support_items=support_items,
        production_state=production_state,
        policy=policy,
        main_sha=main_sha,
        merge_is_on_main=merge_is_on_main,
    )
    if not result.get("source_repair_eligible"):
        reasons = "; ".join(result.get("source_reasons") or ())
        raise RepairRunnerError(
            "REPAIR_ELIGIBILITY_REJECTED",
            "independent J-CHANGE-002 classification rejected candidate: " + reasons[:700],
        )
    if result.get("human_approval_required"):
        raise RepairRunnerError(
            "HUMAN_APPROVAL_REQUIRED",
            "independent classification requires normal human-approved release",
        )
    if str(result.get("support_item") or "") != str(request["support_item"]):
        raise RepairRunnerError(
            "SUPPORT_ITEM_MISMATCH",
            "independent classification support item does not match request",
        )
    return result


def _worktree(repo: Path, candidate: str) -> Path:
    root = Path("/home/al/jason-worktrees/autonomous-repair")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / candidate
    if path.exists():
        shutil.rmtree(path)
    _run(["git", "worktree", "add", "--detach", str(path), candidate], cwd=repo)
    return path


def _remove_worktree(repo: Path, path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _build_candidate(worktree: Path, candidate: str) -> str:
    tag = f"jason-runtime:repair-{candidate[:12]}"
    _run(
        [
            "docker",
            "build",
            "--label",
            f"org.opencontainers.image.revision={candidate}",
            "--label",
            f"com.teamaot.jason.source_revision={candidate}",
            "-t",
            tag,
            "-f",
            str(worktree / "infrastructure" / "jason-runtime" / "Dockerfile"),
            str(worktree),
        ]
    )
    return tag


def _deploy(worktree: Path, image: str, candidate: str) -> None:
    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = image
    env["JASON_SOURCE_REVISION_OVERRIDE"] = candidate
    _run(
        [str(worktree / "infrastructure" / "jason-runtime" / "production-deploy.sh")],
        cwd=worktree,
        env=env,
    )


def _rollback(worktree: Path, rollback_sha: str) -> None:
    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:rollback-current"
    env["JASON_SOURCE_REVISION_OVERRIDE"] = rollback_sha
    _run(
        [str(worktree / "infrastructure" / "jason-runtime" / "production-deploy.sh")],
        cwd=worktree,
        env=env,
    )


def _process(
    *,
    repo: Path,
    spool: Path,
    request_path: Path,
    preflight_only: bool = False,
) -> dict[str, Any]:
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    request = _canonical_request(raw)
    request_id = str(request["request_id"])
    live_before = _live_revision()
    _wait_live_health()
    rollback_sha = str(request["rollback_sha"]).casefold()
    candidate = str(request["candidate_sha"]).casefold()
    if live_before != rollback_sha:
        raise RepairRunnerError(
            "ROLLBACK_REVISION_MISMATCH",
            f"request rollback SHA does not match live runtime revision {live_before}",
        )

    _verify_git(repo, candidate)
    classification = _independent_classification(
        repo=repo,
        request=request,
        live_revision=live_before,
    )
    if preflight_only:
        return {
            "state": "preflight_passed",
            "request_id": request_id,
            "candidate_sha": candidate,
            "rollback_sha": rollback_sha,
            "support_item": request["support_item"],
            "live_revision": live_before,
            "classification": classification.get("classification"),
            "verification_passed": False,
            "rollback_performed": False,
            "completed_at": _now(),
        }

    worktree = _worktree(repo, candidate)
    deployed = False
    try:
        image = _build_candidate(worktree, candidate)
        _deploy(worktree, image, candidate)
        deployed = True
        observed = _live_revision()
        health = _wait_live_health()
        if observed != candidate or health != "healthy":
            raise RepairRunnerError(
                "POST_DEPLOY_VERIFICATION_FAILED",
                f"live verification mismatch revision={observed} health={health}",
            )
        return {
            "state": "succeeded",
            "request_id": request_id,
            "candidate_sha": candidate,
            "rollback_sha": rollback_sha,
            "support_item": request["support_item"],
            "pr_number": request["pr_number"],
            "started_at": request.get("started_at"),
            "completed_at": _now(),
            "live_revision": observed,
            "verification_passed": True,
            "rollback_performed": False,
            "post_deploy_verification": request["post_deploy_verification"],
        }
    except Exception:
        if deployed:
            try:
                _rollback(worktree, rollback_sha)
                rolled_back = (
                    _live_revision() == rollback_sha
                    and _wait_live_health() == "healthy"
                )
            except Exception:
                rolled_back = False
            if not rolled_back:
                raise RepairRunnerError(
                    "ROLLBACK_VERIFICATION_FAILED",
                    "repair deployment failed and rollback could not be verified",
                )
        raise
    finally:
        _remove_worktree(repo, worktree)


def process_one(
    *,
    repo: Path,
    spool: Path,
    preflight_only: bool = False,
) -> bool:
    requests = spool / "requests"
    processing = spool / "processing"
    results = spool / "results"
    for directory in (requests, processing, results):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    candidates = sorted(requests.glob("*.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        return False
    source = candidates[0]
    target = processing / source.name
    os.replace(source, target)

    request_id = source.stem
    started = _now()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        raw["started_at"] = started
        _atomic_json(target.with_suffix(".working.json"), raw)
        os.replace(target.with_suffix(".working.json"), target)
        result = _process(
            repo=repo,
            spool=spool,
            request_path=target,
            preflight_only=preflight_only,
        )
    except RepairRunnerError as error:
        result = {
            "state": "rejected" if not error.code.endswith("FAILED") else "failed",
            "request_id": request_id,
            "started_at": started,
            "completed_at": _now(),
            "error_code": error.code,
            "error_message": str(error)[:700],
            "verification_passed": False,
            "rollback_performed": False,
        }
    except Exception as error:
        result = {
            "state": "failed",
            "request_id": request_id,
            "started_at": started,
            "completed_at": _now(),
            "error_code": type(error).__name__,
            "error_message": str(error)[:700],
            "verification_passed": False,
            "rollback_performed": False,
        }

    _atomic_json(results / source.name, result)
    target.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--spool", type=Path, default=DEFAULT_SPOOL)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    spool = args.spool.expanduser().resolve()
    if not (repo / ".git").exists():
        raise SystemExit("repository root is not a git checkout")

    spool.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = spool / "runner.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        processed = False
        while process_one(
            repo=repo,
            spool=spool,
            preflight_only=args.preflight_only,
        ):
            processed = True
            if args.once:
                break
        print("AUTONOMOUS_REPAIR_RUNNER=" + ("PROCESSED" if processed else "IDLE"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
