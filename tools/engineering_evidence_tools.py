#!/usr/bin/env python3
"""Governed read-only source tools for bounded, resumable engineering reasoning.

Never accepts model-provided shell commands, provider calls, filesystem writes,
authority changes, approvals, CI bypasses, or production deployment requests.
The existing support/development workers remain owners of all code edits.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

POLICY_PATH = "config/engineering-supervisor-policy.json"
ALLOWED = frozenset({"search_source", "read_source"})


class EvidenceToolError(ValueError):
    """Safe explicit blocker; caller must never treat it as an approval."""


def load_policy(repo: Path) -> dict[str, Any]:
    # Treat the fetched authoritative source ref as the configuration authority,
    # never a developer's possibly dirty checked-out repository branch.
    try:
        result = subprocess.run(
            ["git", "show", "origin/main:" + POLICY_PATH],
            cwd=repo, capture_output=True, text=True,
            timeout=10, check=False,
        )
        if result.returncode or len(result.stdout) > 15000:
            raise EvidenceToolError("authoritative engineering evidence policy unavailable")
        payload = json.loads(result.stdout)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        raise EvidenceToolError("authoritative engineering evidence policy unavailable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise EvidenceToolError("invalid engineering evidence policy")
    if type(payload.get("enabled")) is not bool:
        raise EvidenceToolError("invalid evidence enablement")
    ranges = {
        "max_evidence_turns_per_item": (1, 4),
        "max_tool_requests_per_turn": (1, 4),
        "max_sources_per_turn": (1, 12),
        "max_source_chars": (1000, 24000),
        "max_total_source_chars": (2000, 96000),
        "max_previous_sources": (0, 6),
        "max_receipts": (1, 16),
    }
    for key, (small, large) in ranges.items():
        value = payload.get(key)
        if type(value) is not int or not small <= value <= large:
            raise EvidenceToolError("invalid evidence policy bound: " + key)
    tools = payload.get("allowed_read_tools")
    if not isinstance(tools, list) or not tools or set(tools) - ALLOWED:
        raise EvidenceToolError("invalid read-only evidence tools")
    return payload


def _safe_path(worktree: Path, path: str, gate, repair_policy: Mapping[str, Any]) -> bool:
    if (not isinstance(path, str) or not path or len(path) > 240
            or Path(path).is_absolute() or ".." in Path(path).parts
            or any(part.startswith(".") for part in Path(path).parts)):
        return False
    if gate.path_denial_reason(path, dict(repair_policy)):
        return False
    candidate = worktree / path
    if candidate.is_symlink() or not candidate.is_file():
        return False
    if worktree.is_symlink():
        return False
    root = worktree.resolve()
    resolved = candidate.resolve()
    if root not in resolved.parents:
        return False
    # A clean worktree can contain ignored/untracked local credentials. Read
    # only files present in Git's tracked index, never arbitrary working files.
    try:
        listed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=worktree, capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return listed.returncode == 0 and listed.stdout.strip() == path


def execute_tools(
    *,
    worktree: Path,
    requests: list[dict[str, str]],
    gate,
    repair_policy: Mapping[str, Any],
    support,
    policy: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return bounded source excerpts and non-secret auditable receipts.

    Search uses the existing J-CHANGE-002-filtered repository search. Exact
    read_source has additional path traversal, symlink, and containment gates.
    Any unrecognized request fails closed instead of silently dropping it.
    """
    if (not isinstance(requests, list) or not requests
            or len(requests) > policy["max_tool_requests_per_turn"]):
        raise EvidenceToolError("invalid number of source tool requests")
    # Validate the complete batch before executing even a single read.
    # Otherwise a high-volume first search could hide a later denied action.
    for request in requests:
        if not isinstance(request, dict):
            raise EvidenceToolError("invalid source tool request")
        name = request.get("tool")
        if name not in policy["allowed_read_tools"]:
            raise EvidenceToolError("unapproved source tool")
        if set(request) - {"tool", "query", "path"}:
            raise EvidenceToolError("unknown source tool parameters")
        query, path = request.get("query"), request.get("path")
        if name == "search_source":
            if not isinstance(query, str) or not 3 <= len(query.strip()) <= 100 or path:
                raise EvidenceToolError("invalid source search")
        elif not isinstance(path, str) or query or not _safe_path(worktree, path, gate, repair_policy):
            raise EvidenceToolError("source path not authorized")
    excerpts: list[dict[str, str]] = []
    receipts: list[dict[str, str]] = []
    seen: set[str] = set()
    for request in requests:
        name = request["tool"]
        query, path = request.get("query"), request.get("path")
        if name == "search_source":
            candidates = support.safe_search(worktree, [query.strip()], gate, repair_policy)
        else:
            candidates = support.source_excerpts_for_paths(
                worktree, [path], gate, repair_policy,
                limit=1, content_limit=policy["max_source_chars"],
            )
        admitted = 0
        for entry in candidates:
            source = str(entry.get("path") or "")
            if source in seen or not _safe_path(worktree, source, gate, repair_policy):
                continue
            content = str(entry.get("content") or "")[:policy["max_source_chars"]]
            if not content:
                continue
            seen.add(source)
            excerpts.append({"path": source, "content": content})
            receipts.append({
                "tool": name, "path": source,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            })
            admitted += 1
            if len(excerpts) >= policy["max_sources_per_turn"]:
                break
        if admitted == 0:
            receipts.append({"tool": name, "path": "", "sha256": ""})
        if len(excerpts) >= policy["max_sources_per_turn"]:
            break
    if not excerpts:
        raise EvidenceToolError("no authorized source evidence found")
    return excerpts, receipts[:policy["max_receipts"]]


def continue_evidence_session(
    *,
    response_result: Mapping[str, Any],
    record: dict[str, Any],
    item: Mapping[str, Any],
    spool: Path,
    worktree: Path,
    repo: Path,
    gate,
    repair_policy: Mapping[str, Any],
    support,
    queue_reasoning: Callable[..., str],
    context_base: Mapping[str, Any] | None = None,
) -> bool:
    """Consume model read requests and queue one *new* identical-kind reasoning turn.

    Returns False when no model tool request exists. Raises a deterministic
    error on a denied tool/budget so the caller records an explicit blocker.
    """
    raw = response_result.get("evidence_requests")
    if not raw:
        return False
    policy = load_policy(repo)
    if not policy["enabled"]:
        raise EvidenceToolError("engineering evidence turns disabled by policy")
    if response_result.get("edits") or response_result.get("test_paths"):
        raise EvidenceToolError("source request must not be mixed with proposed edits")
    if response_result.get("blocked_reason"):
        raise EvidenceToolError("source request cannot override a terminal blocker")
    round_count = int(record.get("evidence_turn_count") or 0)
    if round_count >= policy["max_evidence_turns_per_item"]:
        raise EvidenceToolError("source evidence turn budget exhausted")
    previous_id = str(record.get("reasoning_request_id") or "")
    if re.fullmatch(r"[a-f0-9]{64}", previous_id) is None:
        raise EvidenceToolError("missing pinned previous reasoning request")
    if record.get("evidence_last_source_request") == previous_id:
        raise EvidenceToolError("source request already processed")
    # Require a clean, pinned source snapshot before any additional discovery.
    if support.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree):
        raise EvidenceToolError("source worktree is dirty")
    head = support.run(["git", "rev-parse", "HEAD"], cwd=worktree)
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise EvidenceToolError("invalid worktree revision")
    authoritative_main = support.run(["git", "rev-parse", "origin/main"], cwd=repo)
    if (re.fullmatch(r"[0-9a-f]{40}", authoritative_main) is None
            or head != authoritative_main):
        raise EvidenceToolError("stale worktree requires governed clean-source recovery")
    excerpts, receipts = execute_tools(
        worktree=worktree, requests=raw, gate=gate,
        repair_policy=repair_policy, support=support, policy=policy,
    )
    # New evidence must be prioritized; keep a small set of previously
    # supplied context, rather than perpetuating the same mistaken 12 files.
    if context_base is None:
        source_path = spool / "reasoning" / "requests" / (previous_id + ".json")
        try:
            if source_path.stat().st_size > 250000:
                raise EvidenceToolError("previous reasoning context too large")
            original = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvidenceToolError("previous reasoning context unavailable") from exc
        if (not isinstance(original, dict)
                or original.get("request_id") != previous_id
                or original.get("kind") != "edit_plan"
                or original.get("support_item") != item["id"]
                or support.request_id(original) != previous_id
                or not isinstance(original.get("context"), dict)):
            raise EvidenceToolError("previous reasoning request failed identity checks")
        context_base = original["context"]
    base = dict(context_base or {})
    # Previous excerpts are not automatically trusted; reread their eligible
    # tracked paths from the same checked-out revision instead of importing
    # potentially stale bytes stored in the prior model request.
    old_paths = []
    for entry in base.get("source_excerpts", []):
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if (isinstance(path, str) and path not in old_paths
                and _safe_path(worktree, path, gate, repair_policy)):
            old_paths.append(path)
        if len(old_paths) >= policy["max_previous_sources"]:
            break
    previous = support.source_excerpts_for_paths(
        worktree, old_paths, gate, repair_policy,
        limit=policy["max_previous_sources"],
        content_limit=policy["max_source_chars"],
    ) if old_paths else []
    combined = support.merge_source_excerpts(
        excerpts, previous,
        max_total=policy["max_sources_per_turn"] + policy["max_previous_sources"],
    )
    total = 0
    bounded = []
    for entry in combined:
        content = str(entry.get("content") or "")[:policy["max_source_chars"]]
        if total + len(content) > policy["max_total_source_chars"]:
            break
        bounded.append({"path": entry["path"], "content": content})
        total += len(content)
    if not bounded:
        raise EvidenceToolError("source evidence size limit exceeded")
    base.update({
        "source_excerpts": bounded,
        "evidence_turn": round_count + 1,
        "previous_reasoning_request_id": previous_id,
        "pinned_source_revision": head,
        "read_only_tool_receipts": receipts,
    })
    # The only permitted output is a new content-addressed model request.
    new_id = queue_reasoning(spool, kind="edit_plan", item=item, context=base)
    if new_id == previous_id or re.fullmatch(r"[a-f0-9]{64}", new_id) is None:
        raise EvidenceToolError("source evidence did not produce a new reasoning request")
    record.update({
        "phase": "implementing",
        "reason": "Bounded read-only source evidence gathered; reasoning continues.",
        "reasoning_request_id": new_id,
        "evidence_last_source_request": previous_id,
        "evidence_turn_count": round_count + 1,
        "evidence_source_revision": head,
        "evidence_last_receipts": receipts,
    })
    return True
