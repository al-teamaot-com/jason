#!/usr/bin/env python3
"""Bridge merged TODO development work into Jason Release Manager."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_REPO = Path("/home/al/projects/jason")
DEFAULT_SPOOL = Path("/var/lib/jason/openclaw/support-repair")
DEFAULT_RELEASE_STATE = Path("/var/lib/jason/openclaw/release-manager")
DEFAULT_RELEASE_RUNNER = Path.home() / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
DEFAULT_RELEASE_SOURCE = Path.home() / ".local" / "lib" / "jason" / "release-manager-source"
WORKTREE_ROOT = Path("/home/al/jason-worktrees/todo-closure")
TODO_PATH = Path("docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md")

TODO_META = re.compile(r"(?im)^\s*-\s*TODO item\s*:\s*(TODO-[A-Z]+-[0-9]+)\s*$")
DEV_META = re.compile(r"(?im)^\s*-\s*Development issue\s*:\s*#([1-9][0-9]*)\s*$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class TodoReleaseBridgeError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and completed.returncode != 0:
        raise TodoReleaseBridgeError(
            f"command failed ({args[0]}): {completed.stdout[-1200:]}"
        )
    return completed.stdout.strip()


def gh_json(args: list[str], *, cwd: Path) -> Any:
    raw = run(["gh", *args], cwd=cwd)
    return json.loads(raw) if raw else None


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "items": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"schema_version": "1.0", "items": {}}


def todo_issues(repo: Path) -> list[dict[str, Any]]:
    issues = gh_json(
        [
            "issue", "list", "--state", "open", "--limit", "200",
            "--json", "number,title,body,url,updatedAt",
        ],
        cwd=repo,
    ) or []
    result = []
    for issue in issues:
        body = str(issue.get("body") or "")
        match = TODO_META.search(body)
        if not match:
            continue
        result.append(
            {
                "todo_id": match.group(1).upper(),
                "issue_number": int(issue["number"]),
                "title": str(issue.get("title") or ""),
                "url": str(issue.get("url") or ""),
                "governing_dependencies": explicit_release_dependencies(body),
            }
        )
    return result


def explicit_release_dependencies(issue_body: str) -> list[str]:
    """Read only machine-explicit release prerequisites, never infer from prose."""
    match = re.search(r"(?im)^\s*-\s*Governing release dependencies\s*:\s*(.+?)\s*$", issue_body)
    if not match:
        return []
    raw = [value.strip() for value in match.group(1).split(",")]
    if not raw or len(raw) > 12 or any(not re.fullmatch(r"release-[0-9a-f]{16}", x) for x in raw):
        return []
    return sorted(set(raw))


def development_records_by_issue(spool: Path) -> dict[int, dict[str, Any]]:
    path = spool / 'development-state.json'
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    items = value.get('items') if isinstance(value, Mapping) else {}
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(items, Mapping):
        return result
    for record in items.values():
        if not isinstance(record, Mapping):
            continue
        raw = record.get('issue_number')
        if not str(raw or '').isdigit():
            continue
        result[int(raw)] = dict(record)
    return result


def upstream_commitment_state(record: Mapping[str, Any] | None) -> tuple[str, str]:
    if not record:
        return (
            'waiting_development_start',
            'Owner-approved TODO has no durable development-worker record.',
        )
    phase = str(record.get('phase') or '').strip()
    reason = str(record.get('reason') or '').strip()
    if phase == 'blocked':
        return 'development_blocked', reason or 'Development worker is blocked.'
    if phase in {
        'waiting_operational_acceptance',
        'waiting_external_dependency',
        'waiting_sequenced_work',
    }:
        return phase, reason
    if phase == 'complete':
        return (
            'development_complete_unmerged',
            reason or 'Development worker says complete but no merged PR was found.',
        )
    if phase in {'pr_ready', 'pr_validating', 'ci_repair_needed', 'ci_repairing'}:
        return 'waiting_development_merge', reason
    return 'development_in_progress', reason


def next_work_gate(phase: str, reason: str) -> dict[str, str]:
    """Classify a pending commitment without granting execution authority."""
    reason_lower = reason.casefold()
    if phase == "complete":
        return {"blocker_category": "none", "next_action": "none"}
    if phase == "waiting_operational_acceptance":
        return {"blocker_category": "acceptance", "next_action": "collect_production_acceptance_evidence"}
    if phase == "waiting_development_merge":
        return {"blocker_category": "merge_gate", "next_action": "recheck_pr_checks_and_merge_readiness"}
    if phase == "closure_validating":
        return {"blocker_category": "closure_gate", "next_action": "recheck_closure_pr_and_todo_readback"}
    if phase == "development_blocked":
        if "dependency" in reason_lower or "prerequisite" in reason_lower:
            return {"blocker_category": "dependency", "next_action": "recheck_authoritative_dependency_acceptance"}
        if "credential" in reason_lower or "api details" in reason_lower or "authorization" in reason_lower:
            return {"blocker_category": "external_authority", "next_action": "request_authorized_provider_access_evidence"}
        if "excerpt" in reason_lower or "source" in reason_lower:
            return {"blocker_category": "source_context", "next_action": "retrieve_bounded_authorized_source_context"}
        if "regression test" in reason_lower:
            return {"blocker_category": "development_test", "next_action": "verify_development_admission_and_author_test"}
        return {"blocker_category": "unknown", "next_action": "classify_from_authoritative_evidence"}
    if phase.startswith("release_") or phase == "waiting_release":
        return {"blocker_category": "release_gate", "next_action": "recheck_governed_release_state"}
    return {"blocker_category": "work_gate", "next_action": "recheck_authoritative_work_state"}


def dependency_recheck_gate(
    item: Mapping[str, Any], accepted_dependencies: Mapping[str, Any]
) -> dict[str, Any]:
    """Report dependency eligibility; never claim a retry or change authority.

    The supplied acceptance map must be constructed from authoritative verified
    releases by a separate governed reader. Missing or partial evidence fails
    closed. A GitHub issue's closed state alone never satisfies this gate.
    """
    if item.get("blocker_category") != "dependency":
        return {"dependency_recheck": "not_applicable", "retry_eligible": False}
    required = item.get("governing_dependencies")
    if not isinstance(required, list) or not required or any(
        not isinstance(value, str) or not value.strip() for value in required
    ):
        return {"dependency_recheck": "missing_dependency_identity", "retry_eligible": False}
    unique = sorted(set(required))
    for dependency in unique:
        proof = accepted_dependencies.get(dependency)
        if not isinstance(proof, Mapping) or proof.get("state") != "production_verified":
            return {"dependency_recheck": "awaiting_verified_dependency", "retry_eligible": False}
        if not isinstance(proof.get("release_sha"), str) or len(proof["release_sha"]) != 40:
            return {"dependency_recheck": "missing_release_provenance", "retry_eligible": False}
    return {"dependency_recheck": "verified_for_governed_readmission_check", "retry_eligible": True}


def accepted_release_dependencies(release_root: Path, identities: list[str]) -> dict[str, Any]:
    """Load exact release IDs only; require a closed release with matching SHA.

    No issue closure, free-text inference, or provider-side mutation qualifies.
    """
    accepted: dict[str, Any] = {}
    for identity in sorted(set(identities)):
        if not re.fullmatch(r"release-[0-9a-f]{16}", identity):
            continue
        candidate = release_root / "records" / (identity + ".json")
        if not candidate.is_file():
            continue
        try:
            record = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        production = record.get("production") or {}
        sha = production.get("live_sha") if isinstance(production, Mapping) else None
        if (record.get("release_id") == identity and record.get("state") == "closed"
                and isinstance(sha, str) and SHA.fullmatch(sha)
                and sha == (record.get("release_manifest") or {}).get("candidate_sha")
                and any(h.get("state") == "closed" and h.get("gate") == "pass"
                        for h in record.get("history", []) if isinstance(h, Mapping))):
            accepted[identity] = {"state": "production_verified", "release_sha": sha}
    return accepted


def dependency_state_for_item(item: Mapping[str, Any], release_root: Path) -> dict[str, Any]:
    required = item.get("governing_dependencies")
    identities = required if isinstance(required, list) else []
    accepted = accepted_release_dependencies(release_root, [s for s in identities if isinstance(s, str)])
    return dependency_recheck_gate(item, accepted)


def commitment_summary(items: Mapping[str, Any]) -> dict[str, Any]:
    phases: dict[str, int] = {}
    outstanding = 0
    blocked = 0
    upstream = 0
    release_pending = 0
    for record in items.values():
        if not isinstance(record, Mapping):
            continue
        phase = str(record.get('phase') or 'unknown')
        phases[phase] = phases.get(phase, 0) + 1
        if phase != 'complete':
            outstanding += 1
        if 'blocked' in phase:
            blocked += 1
        if phase in {
            'waiting_development_start',
            'development_in_progress',
            'development_blocked',
            'development_complete_unmerged',
            'waiting_development_merge',
            'waiting_operational_acceptance',
            'waiting_external_dependency',
            'waiting_sequenced_work',
        }:
            upstream += 1
        if phase in {'waiting_release', 'release_prepare_blocked', 'release_blocked'}:
            release_pending += 1
    return {
        'approved_commitment_count': len([v for v in items.values() if isinstance(v, Mapping)]),
        'outstanding_count': outstanding,
        'blocked_count': blocked,
        'upstream_pending_count': upstream,
        'release_pending_count': release_pending,
        'release_queue_empty_but_upstream_pending': release_pending == 0 and upstream > 0,
        'phases': dict(sorted(phases.items())),
    }


def merged_prs_by_issue(repo: Path) -> dict[int, dict[str, Any]]:
    prs = gh_json(
        [
            "pr", "list", "--state", "merged", "--limit", "200",
            "--json", "number,title,body,url,mergedAt,mergeCommit",
        ],
        cwd=repo,
    ) or []
    result: dict[int, dict[str, Any]] = {}
    for pr in prs:
        match = DEV_META.search(str(pr.get("body") or ""))
        if not match:
            continue
        merge = pr.get("mergeCommit") if isinstance(pr.get("mergeCommit"), Mapping) else {}
        merge_sha = str((merge or {}).get("oid") or "").strip().casefold()
        if not SHA.fullmatch(merge_sha):
            continue
        result[int(match.group(1))] = {
            "pr_number": int(pr["number"]),
            "pr_url": str(pr.get("url") or ""),
            "merge_sha": merge_sha,
            "merged_at": str(pr.get("mergedAt") or ""),
        }
    return result


def release_id(merge_sha: str) -> str:
    if not SHA.fullmatch(merge_sha):
        raise TodoReleaseBridgeError("merge SHA must be exact")
    return "release-" + merge_sha[:16]


def release_record(state_root: Path, merge_sha: str) -> dict[str, Any] | None:
    path = state_root / "records" / f"{release_id(merge_sha)}.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def commit_is_ancestor(repo: Path, ancestor_sha: str, descendant_sha: str) -> bool:
    if not SHA.fullmatch(ancestor_sha) or not SHA.fullmatch(descendant_sha):
        return False
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def effective_release_record(
    repo: Path,
    state_root: Path,
    merge_sha: str,
) -> dict[str, Any] | None:
    exact = release_record(state_root, merge_sha)
    if exact and str(exact.get("state") or "") == "closed":
        return exact

    records = state_root / "records"
    candidates: list[dict[str, Any]] = []
    if records.is_dir():
        for path in records.glob("release-*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or str(value.get("state") or "") != "closed":
                continue
            production = value.get("production") if isinstance(value.get("production"), Mapping) else {}
            live_sha = str(production.get("live_sha") or "").strip().casefold()
            if commit_is_ancestor(repo, merge_sha, live_sha):
                candidates.append(value)
    if candidates:
        candidates.sort(
            key=lambda value: str(
                (value.get("production") or {}).get("verified_at")
                or value.get("updated_at")
                or ""
            ),
            reverse=True,
        )
        return candidates[0]
    return exact


def prepare_release(
    *,
    repo: Path,
    merge_sha: str,
    release_runner: Path,
    release_source: Path,
    release_state: Path,
) -> dict[str, Any]:
    if not release_runner.is_file():
        raise TodoReleaseBridgeError("Release Manager runner is not installed")
    if not release_source.exists():
        raise TodoReleaseBridgeError("Release Manager immutable source is unavailable")
    raw = run(
        [
            "/usr/bin/python3",
            str(release_runner),
            "--repo",
            str(repo),
            "--state-root",
            str(release_state),
            "prepare",
            "--candidate-sha",
            merge_sha,
            "--change-class",
            "todo",
        ],
        cwd=repo,
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TodoReleaseBridgeError("Release Manager prepare returned invalid record")
    return value


def update_todo_text(
    text: str,
    *,
    todo_id: str,
    release: Mapping[str, Any],
) -> str:
    heading = re.search(
        rf"(?im)^###\s+{re.escape(todo_id)}\s+—\s+.+$",
        text,
    )
    if not heading:
        raise TodoReleaseBridgeError(f"TODO item not found: {todo_id}")
    remainder = text[heading.end():]
    next_heading = re.search(
        r"(?im)^###\s+TODO-[A-Z]+-[0-9]+\s+—\s+.+$",
        remainder,
    )
    end = heading.end() + next_heading.start() if next_heading else len(text)
    section = text[heading.start():end]

    if str(release.get("state") or "") != "closed":
        raise TodoReleaseBridgeError("TODO cannot close before Release Manager state closed")
    production = release.get("production") if isinstance(release.get("production"), Mapping) else {}
    sha = str(production.get("live_sha") or "").strip().casefold()
    if not SHA.fullmatch(sha):
        raise TodoReleaseBridgeError("closed release missing production SHA")
    rid = str(release.get("release_id") or "")
    verified = str(production.get("verified_at") or release.get("updated_at") or now())

    status_re = re.compile(r"(?im)^- \*\*Status:\*\*\s*.+$")
    status_line = (
        f"- **Status:** Implemented — production verified {verified}; "
        f"release {rid}; SHA {sha}"
    )
    if status_re.search(section):
        section = status_re.sub(status_line, section, count=1)
    else:
        section = section.rstrip() + "\n" + status_line + "\n"

    evidence_line = (
        f"- **Implementation evidence:** Jason Release Manager {rid} reached "
        f"closed; production SHA {sha}."
    )
    if "**Implementation evidence:**" not in section:
        section = section.rstrip() + "\n" + evidence_line + "\n"

    return text[:heading.start()] + section + text[end:]


def find_closure_pr(repo: Path, todo_id: str) -> dict[str, Any] | None:
    prs = gh_json(
        [
            "pr", "list", "--state", "all", "--limit", "200",
            "--json", "number,title,body,url,mergedAt,state",
        ],
        cwd=repo,
    ) or []
    marker = f"- TODO closure: {todo_id}"
    for pr in prs:
        if marker in str(pr.get("body") or ""):
            return dict(pr)
    return None


def create_closure_pr(
    repo: Path,
    *,
    todo_id: str,
    issue_number: int,
    release: Mapping[str, Any],
) -> int:
    existing = find_closure_pr(repo, todo_id)
    if existing:
        return int(existing["number"])

    production = release.get("production") if isinstance(release.get("production"), Mapping) else {}
    sha = str(production.get("live_sha") or "")
    rid = str(release.get("release_id") or "")
    branch = f"close/todo-{todo_id.casefold()}-{sha[:12]}"
    path = WORKTREE_ROOT / todo_id.casefold()
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)

    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, check=False)
    run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    run(["git", "worktree", "add", "-B", branch, str(path), "origin/main"], cwd=repo)

    backlog = path / TODO_PATH
    original = backlog.read_text(encoding="utf-8")
    updated = update_todo_text(original, todo_id=todo_id, release=release)
    backlog.write_text(updated, encoding="utf-8")

    run(["git", "add", str(TODO_PATH)], cwd=path)
    run(["git", "commit", "-m", f"Close {todo_id} after production verification"], cwd=path)
    run(["git", "push", "-u", "origin", branch], cwd=path)

    body = f"""## TODO production closure

- TODO closure: {todo_id}
- Development issue: #{issue_number}
- Release ID: {rid}
- Production SHA: {sha}
- Release Manager state: closed
- Production verified: yes

## Organizational outcome

Update the governed TODO backlog only after authoritative Release Manager
production verification. No runtime/provider behavior changes in this PR.

## Integration coordination

- Branch baseline SHA: {sha}
- Current-main reconciliation performed: yes
- Integration coordination: none
- Integration automation: enabled
- Production-impacting change: no; documentation-only TODO closure
- Intended production release candidate: none

## Verification

- [x] Release Manager record is closed.
- [x] Production live SHA is exact and recorded.
- [x] TODO status is changed to Implemented with release evidence.

## Documentation impact

- [x] Documentation updated
"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = run(
            [
                "gh", "pr", "create", "--base", "main", "--head", branch,
                "--title", f"Close {todo_id} after production verification",
                "--body-file", str(body_path),
            ],
            cwd=repo,
        )
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r"/pull/(\d+)", raw)
    if not match:
        raise TodoReleaseBridgeError("could not determine TODO closure PR number")
    return int(match.group(1))


def close_issue(repo: Path, issue_number: int, release: Mapping[str, Any]) -> None:
    rid = str(release.get("release_id") or "")
    production = release.get("production") if isinstance(release.get("production"), Mapping) else {}
    sha = str(production.get("live_sha") or "")
    run(
        [
            "gh", "issue", "close", str(issue_number),
            "--comment",
            f"Implemented and production-verified by Jason Release Manager {rid} at {sha}.",
        ],
        cwd=repo,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--spool", type=Path, default=DEFAULT_SPOOL)
    parser.add_argument("--release-state", type=Path, default=DEFAULT_RELEASE_STATE)
    parser.add_argument("--release-runner", type=Path, default=DEFAULT_RELEASE_RUNNER)
    parser.add_argument("--release-source", type=Path, default=DEFAULT_RELEASE_SOURCE)
    args = parser.parse_args()

    repo = args.repo.resolve()
    spool = args.spool.resolve()
    state_path = spool / "todo-release-state.json"
    state = load_state(state_path)
    state.setdefault("items", {})

    run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    prs = merged_prs_by_issue(repo)
    development = development_records_by_issue(spool)

    for issue in todo_issues(repo):
        todo_id = issue["todo_id"]
        record = state["items"].setdefault(
            todo_id,
            {
                "phase": "waiting_development_merge",
                "issue_number": issue["issue_number"],
                "updated_at": now(),
            },
        )
        # Only declared exact release IDs can change the governing dependency
        # set. A changed declaration invalidates the old eligibility result.
        declared = issue["governing_dependencies"]
        if record.get("governing_dependencies") != declared:
            record["governing_dependencies"] = declared
            record.pop("dependency_recheck", None)
            record.pop("retry_eligible", None)
        merged = prs.get(issue["issue_number"])
        if not merged:
            phase, reason = upstream_commitment_state(
                development.get(issue["issue_number"])
            )
            record.update({
                "phase": phase,
                "reason": reason,
                "updated_at": now(),
            })
            continue

        merge_sha = merged["merge_sha"]
        record.update(
            {
                "development_pr": merged["pr_number"],
                "merge_sha": merge_sha,
                "release_id": release_id(merge_sha),
                "updated_at": now(),
            }
        )

        release = effective_release_record(
            repo,
            args.release_state.resolve(),
            merge_sha,
        )
        if release is None:
            try:
                release = prepare_release(
                    repo=repo,
                    merge_sha=merge_sha,
                    release_runner=args.release_runner.expanduser().resolve(),
                    release_source=args.release_source.expanduser().resolve(),
                    release_state=args.release_state.resolve(),
                )
            except Exception as exc:
                record.update(
                    {
                        "phase": "release_prepare_blocked",
                        "reason": f"{type(exc).__name__}: {str(exc)[:900]}",
                        "updated_at": now(),
                    }
                )
                continue

        selected_release_id = str(release.get("release_id") or record["release_id"])
        record["release_id"] = selected_release_id
        if selected_release_id != release_id(merge_sha):
            record["satisfied_by_cumulative_release"] = True
        else:
            record.pop("satisfied_by_cumulative_release", None)
        release_state = str(release.get("state") or "")
        record["release_state"] = release_state

        if release_state == "closed":
            closure = find_closure_pr(repo, todo_id)
            if closure and closure.get("mergedAt"):
                close_issue(repo, issue["issue_number"], release)
                record.update(
                    {
                        "phase": "complete",
                        "closure_pr": int(closure["number"]),
                        "reason": "",
                        "updated_at": now(),
                    }
                )
                continue
            try:
                number = create_closure_pr(
                    repo,
                    todo_id=todo_id,
                    issue_number=issue["issue_number"],
                    release=release,
                )
                record.update(
                    {
                        "phase": "closure_validating",
                        "closure_pr": number,
                        "reason": "",
                        "updated_at": now(),
                    }
                )
            except Exception as exc:
                record.update(
                    {
                        "phase": "closure_blocked",
                        "reason": f"{type(exc).__name__}: {str(exc)[:900]}",
                        "updated_at": now(),
                    }
                )
            continue

        if release_state in {"failed", "rolled_back", "blocked"}:
            record.update(
                {
                    "phase": "release_blocked",
                    "reason": f"Release Manager state is {release_state}",
                    "updated_at": now(),
                }
            )
        else:
            record.update(
                {
                    "phase": "waiting_release",
                    "reason": "",
                    "updated_at": now(),
                }
            )

    for item in state["items"].values():
        if isinstance(item, dict):
            item.update(next_work_gate(str(item.get("phase") or ""), str(item.get("reason") or "")))
    # Read authoritative protected release records, without changing a worker
    # admission decision, modifying dependencies, or granting new authority.
    for item in state["items"].values():
        if isinstance(item, dict):
            item.update(dependency_state_for_item(item, args.release_state.resolve()))
    state["summary"] = commitment_summary(state["items"])
    state["updated_at"] = now()
    atomic_json(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
