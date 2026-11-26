#!/usr/bin/env python3
"""PMV3 governed integration queue and production-candidate merge lock.

Development remains concurrent. PMV3's optional integration queue records
advisory status and never writes protected-branch requirements. The Owner
retired its required status context on 2026-11-10; normal GitHub branch
protection and release governance remain. PMV3 admits only Owner-approved
development evidence (or an explicit integration-ready label), builds a bounded
non-overlapping release train, merges one PR at a time after all existing
required checks pass. Undeployed source backlog is not a production transaction.
The native release manager remains solely responsible for pinned production
candidates, exact approvals, freeze, rollback and verified convergence.

This module has no production deployment authority and never records production
approval. It only controls repository integration under PMV3 standing
engineering authority.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

SCHEMA_VERSION = "1.0"
GATE_CONTEXT = "pmv3-integration-gate"
DEFAULT_REPOSITORY = "al-teamaot-com/jason"
INTEGRATION_READY_LABEL = "pmv3-integration-ready"
RECOVERY_LABEL = "pmv3-release-recovery"
SOURCE_POLICY = "independent_source_v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".pmv3-integration-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_json(path: Path, *, default: Any) -> Any:
    if not path.is_file():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now(),
        "status": "idle",
        "gate_context": GATE_CONTEXT,
        "train": None,
        "release_lock": None,
        "queue": [],
        "metrics": {
            "admitted_open": 0,
            "queued": 0,
            "train_size": 0,
            "merged_in_train": 0,
        },
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_state()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid PMV3 integration queue state")
    if value.get("train") is not None and not isinstance(value.get("train"), dict):
        raise ValueError("invalid PMV3 train state")
    if value.get("release_lock") is not None and not isinstance(value.get("release_lock"), dict):
        raise ValueError("invalid PMV3 release lock state")
    return value


def _labels(pr: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for raw in pr.get("labels") or []:
        if isinstance(raw, Mapping):
            name = str(raw.get("name") or "").strip().casefold()
        else:
            name = str(raw or "").strip().casefold()
        if name:
            result.add(name)
    return result


def approved_pr_numbers(spool: Path) -> set[int]:
    """Return PRs backed by durable Owner-approved development evidence."""
    result: set[int] = set()
    development = load_json(spool / "development-state.json", default={})
    for item in (development.get("items") or {}).values() if isinstance(development, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        pr = item.get("pr_number")
        phase = str(item.get("phase") or "")
        approved_by = str(item.get("approved_by") or "")
        if isinstance(pr, int) and pr > 0 and approved_by and phase in {
            "pr_ready", "complete", "waiting_development_merge"
        }:
            result.add(pr)

    todo = load_json(spool / "todo-release-state.json", default={})
    for item in (todo.get("items") or {}).values() if isinstance(todo, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        pr = item.get("development_pr")
        phase = str(item.get("phase") or "")
        if isinstance(pr, int) and pr > 0 and phase == "waiting_development_merge":
            result.add(pr)
    return result


def production_lkg_revision(release_state: Path) -> str:
    path = release_state / "protected-readback" / "production-control-state.json"
    value = load_json(path, default={})
    if not isinstance(value, Mapping):
        return ""
    manifest = ((value.get("last_known_good") or {}).get("manifest") or {})
    revision = str(manifest.get("revision") or "").strip().casefold()
    return revision if re.fullmatch(r"[0-9a-f]{40}", revision) else ""


def _priority(pr: Mapping[str, Any]) -> tuple[int, str, int]:
    labels = _labels(pr)
    title = str(pr.get("title") or "")
    if RECOVERY_LABEL in labels or title.casefold().startswith("p0 recovery:"):
        rank = -100
    elif any(x in labels for x in {"p0", "priority:p0", "priority-p0"}) or title.casefold().startswith("p0"):
        rank = 0
    elif any(x in labels for x in {"p1", "priority:p1", "priority-p1"}):
        rank = 10
    elif any(x in labels for x in {"p2", "priority:p2", "priority-p2"}):
        rank = 20
    else:
        rank = 100
    return rank, str(pr.get("createdAt") or ""), int(pr.get("number") or 0)


class IntegrationApi(Protocol):
    def main_sha(self) -> str: ...
    def source_ready(self, number: int, head: str, main: str, files: set[str], body=None) -> bool: ...
    def open_pull_requests(self) -> list[dict[str, Any]]: ...
    def pull_request(self, number: int) -> dict[str, Any]: ...
    def changed_files(self, number: int) -> set[str]: ...
    def required_contexts(self) -> list[str]: ...
    def context_states(self, sha: str) -> dict[str, str]: ...
    def set_gate(self, sha: str, state: str, description: str) -> None: ...
    def update_branch(self, number: int, sha: str) -> bool: ...
    def merge_pull_request(self, number: int, sha: str) -> str: ...


class GhApi:
    def __init__(self, repository: str = DEFAULT_REPOSITORY):
        self.repository = repository

    def _run(self, args: list[str], *, input_text: str | None = None) -> str:
        completed = subprocess.run(
            ["gh", *args], text=True, input=input_text,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=45,
            env={**os.environ, "GH_PAGER": "cat", "PAGER": "cat"},
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[:1000]
            raise RuntimeError(f"gh command failed: {detail}")
        return completed.stdout

    def _api_json(self, path: str) -> Any:
        raw = self._run(["api", path])
        return json.loads(raw)

    def main_sha(self) -> str:
        value = self._api_json(f"repos/{self.repository}/branches/main")
        return str(((value.get("commit") or {}).get("sha")) or "")

    def open_pull_requests(self) -> list[dict[str, Any]]:
        """List open main-targeted PRs through paginated REST, not GraphQL.

        Bulk GraphQL discovery can fail independently of commit checks and
        exact selected-PR REST reads. Discovery does not need mergeability;
        the selected PR is refreshed immediately before any merge mutation.
        """
        raw = self._run([
            "api", "--paginate", "--slurp",
            f"repos/{self.repository}/pulls?state=open&base=main&per_page=100",
        ])
        pages = json.loads(raw)
        if not isinstance(pages, list):
            raise RuntimeError("GitHub open pull-request REST response is invalid")
        result: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, list):
                raise RuntimeError("GitHub paginated pull-request page is invalid")
            for value in page:
                if not isinstance(value, Mapping):
                    raise RuntimeError("GitHub pull-request entry is invalid")
                labels = [{"name": str(x.get("name") or "")}
                          for x in value.get("labels") or []
                          if isinstance(x, Mapping)]
                result.append({
                    "number": int(value.get("number") or 0),
                    "title": str(value.get("title") or ""),
                    "isDraft": bool(value.get("draft")),
                    "headRefOid": str(((value.get("head") or {}).get("sha")) or ""),
                    "headRefName": str(((value.get("head") or {}).get("ref")) or ""),
                    "mergeable": "UNKNOWN",
                    "mergeStateStatus": "UNKNOWN",
                    "createdAt": str(value.get("created_at") or ""),
                    "labels": labels,
                    "state": str(value.get("state") or "open"),
                    "merged": bool(value.get("merged")),
                    "mergeCommitSha": str(value.get("merge_commit_sha") or ""),
                    "url": str(value.get("html_url") or ""),
                })
        return result

    def pull_request(self, number: int) -> dict[str, Any]:
        value = self._api_json(f"repos/{self.repository}/pulls/{number}")
        labels = [{"name": str(x.get("name") or "")} for x in value.get("labels") or []]
        return {
            "number": int(value.get("number") or number),
            "title": str(value.get("title") or ""),
            "isDraft": bool(value.get("draft")),
            "headRefOid": str(((value.get("head") or {}).get("sha")) or ""),
            "headRefName": str(((value.get("head") or {}).get("ref")) or ""),
            "baseRefName": str(((value.get("base") or {}).get("ref")) or ""),
            "baseRefOid": str(((value.get("base") or {}).get("sha")) or ""),
            "changedFileCount": value.get("changed_files"),
            "body": str(value.get("body") or ""),
            "mergeable": "MERGEABLE" if value.get("mergeable") is True else (
                "CONFLICTING" if value.get("mergeable") is False else "UNKNOWN"
            ),
            "mergeStateStatus": str(value.get("mergeable_state") or "").upper(),
            "createdAt": str(value.get("created_at") or ""),
            "labels": labels,
            "state": str(value.get("state") or ""),
            "merged": bool(value.get("merged")),
            "mergeCommitSha": str(value.get("merge_commit_sha") or ""),
        }

    def changed_files(self, number: int) -> set[str]:
        raw = self._run([
            "api", "--paginate", f"repos/{self.repository}/pulls/{number}/files?per_page=100",
            "--jq", ".[].filename",
        ])
        return {line.strip() for line in raw.splitlines() if line.strip()}

    def required_contexts(self) -> list[str]:
        value = self._api_json(
            f"repos/{self.repository}/branches/main/protection/required_status_checks"
        )
        return [str(x) for x in value.get("contexts") or [] if str(x) != GATE_CONTEXT]

    def context_states(self, sha: str) -> dict[str, str]:
        result: dict[str, str] = {}
        checks = self._api_json(f"repos/{self.repository}/commits/{sha}/check-runs?per_page=100")
        for check in checks.get("check_runs") or []:
            name = str(check.get("name") or "")
            if not name or name in result:
                continue
            status = str(check.get("status") or "")
            conclusion = str(check.get("conclusion") or "")
            if status == "completed" and conclusion in {"success", "neutral", "skipped"}:
                result[name] = "success"
            elif status == "completed":
                result[name] = "failure"
            else:
                result[name] = "pending"
        combined = self._api_json(f"repos/{self.repository}/commits/{sha}/status")
        for status in combined.get("statuses") or []:
            name = str(status.get("context") or "")
            if name and name not in result:
                result[name] = str(status.get("state") or "pending")
        return result

    def set_gate(self, sha: str, state: str, description: str) -> None:
        description = description[:140]
        combined = self._api_json(f"repos/{self.repository}/commits/{sha}/status")
        for status in combined.get("statuses") or []:
            if str(status.get("context") or "") != GATE_CONTEXT:
                continue
            if (str(status.get("state") or "") == state
                    and str(status.get("description") or "") == description):
                return
            break
        self._run([
            "api", "--method", "POST", f"repos/{self.repository}/statuses/{sha}",
            "-f", f"state={state}", "-f", f"context={GATE_CONTEXT}",
            "-f", "target_url=https://github.com/al-teamaot-com/jason",
            "-f", f"description={description}", "--silent",
        ])

    def update_branch(self, number: int, sha: str) -> bool:
        try:
            self._run([
                "api", "--method", "PUT", f"repos/{self.repository}/pulls/{number}/update-branch",
                "-f", f"expected_head_sha={sha}", "--silent",
            ])
            return True
        except RuntimeError:
            return False

    def source_ready(self, number: int, head: str, main: str, files: set[str], body=None) -> bool:
        branch = self._api_json(f"repos/{self.repository}/branches/main")
        policy = self._api_json(f"repos/{self.repository}/branches/main/protection/required_status_checks")
        if (branch.get("protected") is not True
                or (branch.get("commit") or {}).get("sha") != main
                or policy.get("strict") is not True
                or "repository-hygiene" not in policy.get("contexts", [])):
            return False
        compare = self._api_json(f"repos/{self.repository}/compare/{main}...{head}")
        if (compare.get("status") not in {"ahead", "identical"}
                or (compare.get("merge_base_commit") or {}).get("sha") != main):
            return False
        fresh = self.pull_request(number)
        try:
            from change_integration_gate import active_overlap_check
        except ModuleNotFoundError:
            from tools.change_integration_gate import active_overlap_check

        def pages(url, _token):
            prefix = f"https://api.github.com/repos/{self.repository}/"
            if not url.startswith(prefix):
                raise PermissionError("SOURCE_OVERLAP_REVIEW_URL")
            payload = json.loads(self._run(["api", "--paginate", "--slurp",
                                           url.removeprefix("https://api.github.com/")]))
            if not isinstance(payload, list) or any(not isinstance(x, list) for x in payload):
                raise ValueError("SOURCE_OVERLAP_REVIEW_INCOMPLETE")
            return [row for page in payload for row in page]

        return (fresh.get("state") == "open" and fresh.get("isDraft") is False
                and fresh.get("baseRefName") == "main"
                and fresh.get("baseRefOid") == main
                and fresh.get("headRefOid") == head
                and (body is None or fresh.get("body") == body)
                and type(fresh.get("changedFileCount")) is int
                and fresh["changedFileCount"] == len(files)
                and self.changed_files(number) == files
                and not active_overlap_check(self.repository, number, "main", files,
                                             fresh["body"], "", 7, read_pages=pages)
                and self.main_sha() == main)

    def merge_pull_request(self, number: int, sha: str) -> str:
        raw = self._run([
            "api", "--method", "PUT", f"repos/{self.repository}/pulls/{number}/merge",
            "-f", f"sha={sha}", "-f", "merge_method=squash",
        ])
        value = json.loads(raw)
        if value.get("merged") is not True:
            raise RuntimeError("GitHub did not merge selected PR: " + str(value.get("message") or "unknown"))
        merged_sha = str(value.get("sha") or "")
        if len(merged_sha) != 40:
            raise RuntimeError("merged PR did not return exact SHA")
        return merged_sha


def checks_ready(api: IntegrationApi, sha: str) -> tuple[bool, list[str]]:
    required = api.required_contexts()
    states = api.context_states(sha)
    missing = [name for name in required if states.get(name) != "success"]
    return not missing, missing


def _is_admitted(pr: Mapping[str, Any], durable: set[int]) -> bool:
    number = int(pr.get("number") or 0)
    return number in durable or INTEGRATION_READY_LABEL in _labels(pr)


def _queue_view(prs: Iterable[Mapping[str, Any]], durable: set[int]) -> list[dict[str, Any]]:
    result = []
    for pr in prs:
        if not _is_admitted(pr, durable):
            continue
        result.append({
            "pr_number": int(pr.get("number") or 0),
            "title": str(pr.get("title") or ""),
            "head_sha": str(pr.get("headRefOid") or ""),
            "priority": _priority(pr)[0],
        })
    result.sort(key=lambda x: (int(x["priority"]), int(x["pr_number"])))
    return result


def select_train(
    api: IntegrationApi,
    prs: list[dict[str, Any]],
    durable: set[int],
    *,
    batch_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [
        pr for pr in prs
        if _is_admitted(pr, durable)
        and not bool(pr.get("isDraft"))
        and str(pr.get("mergeable") or "").upper() != "CONFLICTING"
    ]
    candidates.sort(key=_priority)
    selected: list[dict[str, Any]] = []
    used_files: set[str] = set()
    waiting: list[dict[str, Any]] = []
    for pr in candidates:
        if len(selected) >= max(1, int(batch_size)):
            waiting.append(pr)
            continue
        sha = str(pr.get("headRefOid") or "")
        ready, missing = checks_ready(api, sha)
        if not ready:
            copy = dict(pr)
            copy["queue_reason"] = "required_checks_pending:" + ",".join(missing[:8])
            waiting.append(copy)
            continue
        files = api.changed_files(int(pr["number"]))
        if selected and files.intersection(used_files):
            copy = dict(pr)
            copy["queue_reason"] = "overlaps_current_release_train"
            waiting.append(copy)
            continue
        copy = dict(pr)
        copy["files"] = sorted(files)
        selected.append(copy)
        used_files.update(files)
    return selected, waiting


def _set_all_pending(api: IntegrationApi, prs: Iterable[Mapping[str, Any]], description: str) -> None:
    for pr in prs:
        sha = str(pr.get("headRefOid") or "")
        if len(sha) == 40:
            api.set_gate(sha, "pending", description)


def _make_train(main_sha: str, selected: list[dict[str, Any]]) -> dict[str, Any]:
    stamp = now()
    return {
        "train_id": "train-" + main_sha[:12] + "-" + stamp.replace(":", "").replace("+", "")[-14:],
        "base_main_sha": main_sha,
        "started_at": stamp,
        "status": "integrating",
        "prs": [
            {
                "pr_number": int(pr["number"]),
                "title": str(pr.get("title") or ""),
                "head_sha": str(pr.get("headRefOid") or ""),
                "files": list(pr.get("files") or []),
                "state": "queued",
            }
            for pr in selected
        ],
        "merged": [],
        "skipped": [],
    }


def _current_train_pr(train: Mapping[str, Any]) -> dict[str, Any] | None:
    for item in train.get("prs") or []:
        if isinstance(item, dict) and item.get("state") == "queued":
            return item
    return None


def _release_lock(candidate_sha: str, train: Mapping[str, Any] | None, *, reason: str) -> dict[str, Any]:
    return {
        "active": True,
        "candidate_sha": candidate_sha,
        "train_id": (train or {}).get("train_id"),
        "locked_at": now(),
        "reason": reason,
    }


def _recovery_candidate(prs: list[dict[str, Any]], durable: set[int]) -> dict[str, Any] | None:
    candidates = [
        pr for pr in prs
        if _is_admitted(pr, durable)
        and RECOVERY_LABEL in _labels(pr)
        and not bool(pr.get("isDraft"))
        and str(pr.get("mergeable") or "").upper() != "CONFLICTING"
    ]
    candidates.sort(key=_priority)
    return candidates[0] if candidates else None


class SourceIntegrationDeferred(PermissionError):
    """A real production transaction owns the mutex; no source mutation."""


@contextmanager
def trusted_flock(path: Path, mode: int, *, create: bool = False):
    flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY), 0o600)
    try:
        def validate():
            st = os.fstat(fd)
            current = path.lstat()
            if (not stat.S_ISREG(st.st_mode) or not stat.S_ISREG(current.st_mode)
                    or st.st_uid != os.getuid() or current.st_uid != os.getuid()
                    or st.st_mode & 0o002 or current.st_mode & 0o002
                    or (create and (st.st_mode & 0o077 or current.st_mode & 0o077))
                    or (current.st_dev, current.st_ino) != (st.st_dev, st.st_ino)):
                raise PermissionError("SOURCE_INTEGRATION_LOCK_UNTRUSTED_OR_REPLACED")
            return st.st_dev, st.st_ino

        validate()
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        validate()
        yield validate
    finally:
        os.close(fd)


@contextmanager
def source_mutex(spool: Path, release_state: Path):
    """Serialize queue reconciliation, leasing production only for mutation.

    Long source reviews need no production lock. Before actual mutation,
    reacquire the original native mutex and recheck all changing identities.
    Never create or replace the production lock.
    """
    lock = release_state / "production-transaction.lock"
    pause = spool / "pmv3-engineering-owner-pause.json"
    with trusted_flock(spool / ".pmv3-source-integration.lock", fcntl.LOCK_EX, create=True) as queue_guard:
        if queue_guard is None or os.path.lexists(pause):
            yield None
            return
        with trusted_flock(lock, fcntl.LOCK_SH) as probe:
            if probe is None:
                yield None
                return
            original_inode = probe()
        @contextmanager
        def mutation_guard():
            with trusted_flock(lock, fcntl.LOCK_SH) as production_guard:
                if production_guard is None:
                    raise SourceIntegrationDeferred("SOURCE_INTEGRATION_PRODUCTION_BUSY")
                def validate():
                    queue_guard()
                    if production_guard() != original_inode:
                        raise PermissionError("SOURCE_INTEGRATION_LOCK_REPLACED")
                    if os.path.lexists(pause):
                        raise PermissionError("SOURCE_INTEGRATION_PAUSED")
                validate()
                yield validate
        yield mutation_guard


def reconcile(*, api: IntegrationApi, spool: Path, release_state: Path,
              state_path: Path | None = None, batch_size: int = 3,
              independent_source: bool = True) -> dict[str, Any]:
    if not independent_source:
        return _reconcile(api=api, spool=spool, release_state=release_state,
                          state_path=state_path, batch_size=batch_size, independent_source=False)
    with source_mutex(spool, release_state) as admitted:
        if not admitted:
            state = load_state(state_path or spool / "pmv3-integration-queue-state.json")
            return {**state, "status": "source_integration_deferred",
                    "integration_policy": SOURCE_POLICY, "production_authority": False}
        try:
            return _reconcile(api=api, spool=spool, release_state=release_state,
                              state_path=state_path, batch_size=batch_size, independent_source=True,
                              mutation_guard=admitted)
        except SourceIntegrationDeferred:
            state = load_state(state_path or spool / "pmv3-integration-queue-state.json")
            return {**state, "status": "source_integration_deferred",
                    "integration_policy": SOURCE_POLICY, "production_authority": False}


def _reconcile(*, api: IntegrationApi, spool: Path, release_state: Path,
               state_path: Path | None, batch_size: int,
               independent_source: bool, mutation_guard=None) -> dict[str, Any]:
    state_path = state_path or (spool / "pmv3-integration-queue-state.json")
    state = load_state(state_path)
    # Owner retired the PMV3 GitHub required-status context on 2026-11-10.
    # This queue may still publish advisory status, but must never reconfigure
    # protected-branch requirements or restore that self-imposed merge gate.
    main_sha = api.main_sha()
    if independent_source and not re.fullmatch(r"[0-9a-f]{40}", main_sha):
        raise ValueError("authoritative protected main SHA is unavailable")
    lkg_sha = production_lkg_revision(release_state)
    prs = api.open_pull_requests()
    durable = approved_pr_numbers(spool)
    admitted_open = [pr for pr in prs if _is_admitted(pr, durable)]
    state["queue"] = _queue_view(prs, durable)
    state["main_sha"] = main_sha
    state["production_lkg_sha"] = lkg_sha

    lock = state.get("release_lock") if isinstance(state.get("release_lock"), dict) else None
    train = state.get("train") if isinstance(state.get("train"), dict) else None

    source_allowed = bool(independent_source and lkg_sha)
    if independent_source:
        state["integration_policy"] = SOURCE_POLICY
        state["production_authority"] = False
        if not source_allowed:
            if train is not None:
                state["suspended_source_train"] = train
            state["train"] = None
            train = None
        elif lock:
            archived = list(state.get("legacy_release_locks") or [])
            if lock not in archived:
                archived.append(lock)
            state["legacy_release_locks"] = archived
            state["release_lock"] = None
            lock = None

    def pending(items, description):
        if not independent_source:
            _set_all_pending(api, items, description)

    @contextmanager
    def check_mutation(number, sha, files, reviewed_body, *, merge=False):
        if not independent_source:
            yield
            return
        with mutation_guard() as validate:
            validate()
            fresh = api.pull_request(number)
            if (fresh.get("state") != "open" or fresh.get("isDraft") is not False
                    or fresh.get("baseRefName") != "main" or fresh.get("headRefOid") != sha
                    or fresh.get("body") != reviewed_body
                    or not _is_admitted(fresh, approved_pr_numbers(spool))
                    or api.changed_files(number) != set(files)
                    or api.main_sha() != main_sha
                    or production_lkg_revision(release_state) != lkg_sha):
                raise PermissionError("SOURCE_INTEGRATION_REVIEW_CHANGED")
            if merge:
                ready, _ = checks_ready(api, sha)
                if (not ready or not api.required_contexts()
                        or fresh.get("mergeable") != "MERGEABLE"
                        or fresh.get("mergeStateStatus") not in {"CLEAN", "UNSTABLE"}):
                    raise PermissionError("SOURCE_INTEGRATION_REQUIRED_CHECKS_CHANGED")
            validate()
            yield

    # A completed and accepted release unlocks legacy integration automatically.
    if lock and lkg_sha and lkg_sha == str(lock.get("candidate_sha") or ""):
        state["release_lock"] = None
        lock = None

    # Fail closed after restart or external main movement: any source delta from
    # verified production becomes the active candidate lock unless a train is
    # already deliberately building that candidate.
    if train is None and main_sha and not lkg_sha:
        if not lock or str(lock.get("candidate_sha") or "") != main_sha:
            state["release_lock"] = _release_lock(
                main_sha, None, reason="verified_production_revision_unknown"
            )
            lock = state["release_lock"]
    elif not source_allowed and train is None and main_sha and lkg_sha and main_sha != lkg_sha:
        if not lock or str(lock.get("candidate_sha") or "") != main_sha:
            state["release_lock"] = _release_lock(
                main_sha, None, reason="main_ahead_of_verified_production"
            )
            lock = state["release_lock"]

    if lock:
        # Recovery PRs are the only integration allowed while a release lock is
        # active, and only with explicit PMV3 recovery labeling plus normal
        # durable admission and all existing required checks.
        recovery = None if independent_source else _recovery_candidate(prs, durable)
        if recovery is not None:
            # Discovery carries no mergeability assertion. Re-read the exact
            # selected recovery PR before setting its gate or merging it.
            recovery = api.pull_request(int(recovery["number"]))
            recovery_labels = _labels(recovery)
            if (recovery.get("state") != "open"
                    or bool(recovery.get("isDraft"))
                    or RECOVERY_LABEL not in recovery_labels
                    or not _is_admitted(recovery, durable)
                    or str(recovery.get("mergeable") or "").upper() == "CONFLICTING"
                    or str(recovery.get("mergeStateStatus") or "").upper() == "DIRTY"):
                recovery = None
        if recovery is not None:
            rsha = str(recovery.get("headRefOid") or "")
            ready, missing = checks_ready(api, rsha)
            if ready:
                api.set_gate(rsha, "success", "PMV3 selected bounded release-recovery PR")
                merged_sha = api.merge_pull_request(int(recovery["number"]), rsha)
                # GitHub's merge is already durable. Checkpoint the NEW protected
                # candidate before making further status API calls: a network or
                # status-write failure must not leave an obsolete release lock.
                state["main_sha"] = merged_sha
                state["release_lock"] = _release_lock(
                    merged_sha, None, reason="release_recovery_candidate_merged"
                )
                state["status"] = "release_locked"
                state["last_action"] = {
                    "action": "merged_release_recovery_pr",
                    "pr_number": int(recovery["number"]),
                    "candidate_sha": merged_sha,
                    "at": now(),
                }
                state["queue"] = [
                    item for item in state["queue"]
                    if int(item.get("pr_number") or 0) != int(recovery["number"])
                ]
                admitted_open = [
                    item for item in admitted_open
                    if int(item.get("number") or 0) != int(recovery["number"])
                ]
                atomic_json(state_path, state)
                api.set_gate(
                    merged_sha, "success",
                    "PMV3 integrated selected release-recovery PR; exact candidate locked",
                )
                pending([pr for pr in prs if int(pr.get("number") or 0) != int(recovery["number"])],
                                 "PMV3 release candidate locked; development continues")
            else:
                api.set_gate(rsha, "pending", "PMV3 recovery PR waiting required checks")
                state["status"] = "release_locked"
                state["last_action"] = {"action": "recovery_waiting_checks", "missing": missing[:12], "at": now()}
        else:
            pending(prs, "PMV3 release candidate locked; development continues")
            state["status"] = "release_locked"
            state["last_action"] = {"action": "hold_integration_for_release", "at": now()}
        state["train"] = None
    else:
        if train is None:
            selected, waiting = select_train(api, prs, durable, batch_size=batch_size)
            if selected:
                train = _make_train(main_sha, selected)
                state["train"] = train
                state["status"] = "integrating"
                state["last_action"] = {
                    "action": "release_train_selected",
                    "train_id": train["train_id"],
                    "pr_numbers": [int(x["pr_number"]) for x in train["prs"]],
                    "at": now(),
                }
            else:
                pending(prs, "PMV3 queue: not selected for integration")
                state["status"] = "idle"
                state["last_action"] = {"action": "no_ready_approved_prs", "at": now()}
                state["waiting"] = [
                    {"pr_number": int(x.get("number") or 0), "reason": x.get("queue_reason", "not_ready")}
                    for x in waiting[:20]
                ]

        if train is not None:
            current = _current_train_pr(train)
            if current is None:
                final_sha = api.main_sha()
                state["main_sha"] = final_sha
                state["release_lock"] = (None if source_allowed else _release_lock(
                    final_sha, train, reason="release_train_complete_awaiting_production"))
                state["train"] = None
                state["status"] = "source_backlog" if source_allowed else "release_locked"
                pending(prs, "PMV3 release train complete; awaiting production")
            else:
                number = int(current["pr_number"])
                fresh = api.pull_request(number)
                if fresh.get("state") == "closed" and fresh.get("merged") is True:
                    current["state"] = "merged"
                    current["merge_sha"] = str(fresh.get("mergeCommitSha") or "")
                    train["merged"].append(number)
                elif fresh.get("state") == "closed":
                    current["state"] = "skipped"
                    current["reason"] = "closed_without_merge"
                    train["skipped"].append(number)
                else:
                    sha = str(fresh.get("headRefOid") or "")
                    current["head_sha"] = sha
                    pending(
                        [pr for pr in prs if int(pr.get("number") or 0) != number],
                        f"PMV3 queue: release train {train['train_id']} in progress",
                    )
                    mergeability = str(fresh.get("mergeable") or "").upper()
                    merge_state = str(fresh.get("mergeStateStatus") or "").upper()
                    if independent_source and (
                            fresh.get("state") != "open" or fresh.get("isDraft") is not False
                            or fresh.get("baseRefName") != "main"
                            or not _is_admitted(fresh, approved_pr_numbers(spool))
                            or not re.fullmatch(r"[0-9a-f]{40}", sha)
                            or set(current["files"]) != api.changed_files(number)):
                        current["state"] = "skipped"
                        current["reason"] = "fresh_source_admission_or_scope_changed"
                        train["skipped"].append(number)
                        state["last_action"] = {"action": "source_review_required", "pr_number": number, "at": now()}
                    elif mergeability == "CONFLICTING" or merge_state == "DIRTY":
                        api.set_gate(sha, "pending", "PMV3 selected PR has merge conflict; skipped from train")
                        current["state"] = "skipped"
                        current["reason"] = "merge_conflict"
                        train["skipped"].append(number)
                        state["last_action"] = {"action": "skipped_conflicting_pr", "pr_number": number, "at": now()}
                    elif mergeability == "UNKNOWN" or merge_state == "UNKNOWN":
                        api.set_gate(sha, "pending", "PMV3 selected; waiting for GitHub mergeability")
                        state["last_action"] = {"action": "waiting_mergeability", "pr_number": number, "at": now()}
                    elif merge_state == "BEHIND":
                        if independent_source and (api.main_sha() != main_sha or
                                os.path.lexists(spool / "pmv3-engineering-owner-pause.json")):
                            raise PermissionError("SOURCE_INTEGRATION_BASE_OR_PAUSE_CHANGED")
                        api.set_gate(sha, "pending", "PMV3 selected; updating branch to current main")
                        with check_mutation(number, sha, current["files"], fresh.get("body")):
                            updated = api.update_branch(number, sha)
                        if not updated:
                            current["state"] = "skipped"
                            current["reason"] = "unable_to_update_branch"
                            train["skipped"].append(number)
                        else:
                            state["last_action"] = {"action": "updated_selected_pr_branch", "pr_number": number, "at": now()}
                    else:
                        ready, missing = checks_ready(api, sha)
                        if not ready or (independent_source and (
                                mergeability != "MERGEABLE" or merge_state not in {"CLEAN", "UNSTABLE"}
                                or not api.required_contexts()
                                or not api.source_ready(number, sha, main_sha, set(current["files"]), fresh.get("body"))
                                or os.path.lexists(spool / "pmv3-engineering-owner-pause.json")
                                or production_lkg_revision(release_state) != lkg_sha)):
                            api.set_gate(sha, "pending", "PMV3 selected; waiting required checks or exact source review")
                            state["last_action"] = {
                                "action": "selected_pr_waiting_checks", "pr_number": number,
                                "missing": missing[:12], "at": now(),
                            }
                        else:
                            if not independent_source:
                                api.set_gate(sha, "success", f"PMV3 selected in {train['train_id']}")
                            with check_mutation(number, sha, current["files"], fresh.get("body"), merge=True):
                                merged_sha = api.merge_pull_request(number, sha)
                            state["main_sha"] = merged_sha
                            current["state"] = "merged"
                            current["merge_sha"] = merged_sha
                            train["merged"].append(number)
                            state["last_action"] = {
                                "action": "merged_selected_pr", "pr_number": number,
                                "merge_sha": merged_sha, "at": now(),
                            }
                            if independent_source:
                                state["source_backlog"] = {"main_sha": merged_sha, "verified_production_sha": lkg_sha,
                                    "pending_production_review": merged_sha != lkg_sha, "production_authority": False}
                            atomic_json(state_path, state)
                            api.set_gate(merged_sha, "success", f"PMV3 integrated selected PR in {train['train_id']}")
                if _current_train_pr(train) is None:
                    final_sha = api.main_sha()
                    state["main_sha"] = final_sha
                    state["release_lock"] = (None if source_allowed else _release_lock(
                        final_sha, train, reason="release_train_complete_awaiting_production"))
                    state["train"] = None
                    state["status"] = "source_backlog" if source_allowed else "release_locked"
                    if not independent_source:
                        pending(api.open_pull_requests(), "PMV3 release train complete; awaiting production")
                else:
                    state["status"] = "integrating"

    if independent_source:
        state["source_backlog"] = {"main_sha": state["main_sha"], "verified_production_sha": lkg_sha,
            "pending_production_review": bool(lkg_sha and state["main_sha"] != lkg_sha),
            "production_authority": False}
        if state["status"] in {"idle", "source_backlog"}:
            state["status"] = "source_backlog" if state["source_backlog"]["pending_production_review"] else "idle"
    active_train = state.get("train") if isinstance(state.get("train"), dict) else None
    state["metrics"] = {
        "admitted_open": len(admitted_open),
        "queued": len(state.get("queue") or []),
        "train_size": len((active_train or {}).get("prs") or []),
        "merged_in_train": len((active_train or {}).get("merged") or []),
        "release_locked": bool(state.get("release_lock")),
    }
    state["updated_at"] = now()
    atomic_json(state_path, state)
    return state


def snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    train = state.get("train") if isinstance(state.get("train"), Mapping) else None
    lock = state.get("release_lock") if isinstance(state.get("release_lock"), Mapping) else None
    return {
        "status": str(state.get("status") or "unknown"),
        "gate_context": GATE_CONTEXT,
        "main_sha": state.get("main_sha"),
        "production_lkg_sha": state.get("production_lkg_sha"),
        "release_lock_active": bool(lock),
        "release_candidate_sha": (lock or {}).get("candidate_sha"),
        "integration_policy": state.get("integration_policy", "legacy"),
        "source_backlog": state.get("source_backlog"),
        "production_authority": False,
        "train_id": (train or {}).get("train_id"),
        "train_prs": [int(x.get("pr_number") or 0) for x in (train or {}).get("prs") or []],
        "queue_depth": len(state.get("queue") or []),
        "last_action": state.get("last_action"),
        "updated_at": state.get("updated_at"),
    }


def current_status(*, api: IntegrationApi, spool: Path, release_state: Path,
                   independent_source: bool = True) -> dict[str, Any]:
    """Read live SHA identities without advancing or mutating the integration queue.

    A paused queue may retain its previous cycle after an accepted deployment.
    Report it as pending reconciliation, not as a pending deployment. Its
    durable lock is left intact for the next governed queue cycle.
    """
    state = load_state(spool / "pmv3-integration-queue-state.json")
    main_sha = api.main_sha().strip().casefold()
    if len(main_sha) != 40 or any(c not in "0123456789abcdef" for c in main_sha):
        raise ValueError("authoritative protected main SHA is unavailable")
    lkg_sha = production_lkg_revision(release_state)
    result = snapshot(state)
    result["stored_main_sha"] = state.get("main_sha")
    result["stored_production_lkg_sha"] = state.get("production_lkg_sha")
    result["main_sha"] = main_sha
    result["production_lkg_sha"] = lkg_sha
    result["readback_at"] = now()
    result["queue_state_stale"] = (
        state.get("main_sha") != main_sha
        or state.get("production_lkg_sha") != lkg_sha
    )
    lock = state.get("release_lock") if isinstance(state.get("release_lock"), Mapping) else None
    completed = bool(lock and main_sha == lkg_sha
                     and str(lock.get("candidate_sha") or "") == main_sha)
    result["release_lock_reconciliation_pending"] = completed
    if independent_source and lkg_sha:
        result["integration_policy"] = SOURCE_POLICY
        result["source_backlog"] = {"main_sha": main_sha, "verified_production_sha": lkg_sha,
                                    "pending_production_review": main_sha != lkg_sha,
                                    "production_authority": False}
        if state.get("integration_policy") != SOURCE_POLICY or lock:
            result["status"] = "source_policy_reconciliation_pending"
        elif main_sha != lkg_sha and not isinstance(state.get("train"), Mapping):
            result["status"] = "source_backlog"
    elif not lkg_sha or main_sha != lkg_sha:
        result["status"] = "release_locked"
    elif completed:
        result["status"] = "release_complete_pending_queue_refresh"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--release-state", type=Path, required=True)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--status-only", action="store_true",
                        help="Read current GitHub/production revisions without changing queue state")
    args = parser.parse_args()
    if args.status_only:
        try:
            status = current_status(
                api=GhApi(args.repository), spool=args.spool.resolve(),
                release_state=args.release_state.resolve(),
            )
        except Exception as exc:
            print("PMV3_INTEGRATION_QUEUE " + json.dumps({
                "status": "control_failure", "error_type": type(exc).__name__,
                "reason": str(exc)[:500],
            }, sort_keys=True))
            return 1
        print("PMV3_INTEGRATION_QUEUE " + json.dumps(status, sort_keys=True))
        return 0
    try:
        state = reconcile(
            api=GhApi(args.repository), spool=args.spool.resolve(),
            release_state=args.release_state.resolve(),
            batch_size=max(1, min(10, int(args.batch_size))),
        )
    except Exception as exc:
        # Fail closed: the required gate remains pending/missing and therefore
        # GitHub blocks integration. Development/CI may continue independently.
        print("PMV3_INTEGRATION_QUEUE " + json.dumps({
            "status": "control_failure", "error_type": type(exc).__name__,
            "reason": str(exc)[:500],
        }, sort_keys=True))
        return 1
    print("PMV3_INTEGRATION_QUEUE " + json.dumps(snapshot(state), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
