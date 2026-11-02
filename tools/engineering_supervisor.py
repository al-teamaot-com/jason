#!/usr/bin/env python3
"""Persistent, read-only, fail-closed supervisor of approved engineering progress.

Only native support, development and release workers may claim or mutate jobs.
This supervisor classifies their states, monitors lack of forward progress and
provides concrete next-action routing; it cannot approve, deploy or retry work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("invalid supervisor state source: " + name)
    return raw


def atomic_write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".engineering-supervisor-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def classify(phase: str, reason: str, *, lane: str) -> tuple[str, str]:
    """Separate internal recovery from genuine external gates.

    Pure classification changes no persisted worker phase, admission capacity,
    owner authority, or workflow; unknown blockers are never auto-retried.
    """
    text = reason.casefold()
    if phase in {"complete", "closed"}:
        return "complete", "none"
    if phase in {"pr_ready", "waiting_development_merge", "pr_validating"}:
        return "integration_review", "complete_governed_pr_review"
    if phase in {"production_eligible", "waiting_release"}:
        return "release_approval", "follow_exact_sha_approval_workflow"
    if phase in {"waiting_operational_acceptance", "production_verifying"}:
        return "acceptance", "verify_actual_production_outcome"
    if phase in {"identified", "diagnosing", "implementing", "ci_repair_needed", "ci_repairing"}:
        return "active", "continue_native_worker"
    if phase not in {"blocked", "escalated", "development_blocked", "waiting_external_dependency"}:
        return "needs_triage", "inspect_bounded_state_evidence"
    if "credit_balance_exhausted" in text:
        return "recoverable_credit", "pmv3_verify_hosted_credit_then_readmit"
    if any(term in text for term in ("credential", "api details", "api access", "provider license",
                                      "billing credits", "tenant permission")):
        return "external_dependency", "obtain_authorized_provider_dependency"
    if any(term in text for term in ("prerequisite", "blocked by dependency", "after support-cap",
                                      "do not begin", "gate hold", "until the prerequisite")):
        return "dependency_hold", "verify_and_clear_authoritative_prerequisite"
    if any(term in text for term in ("owner approval", "must approve", "unauthorized",
                                      "explicit authority", "identity not verified")):
        return "human_authority", "request_verified_human_authorization"
    if "recovery worktree does not match its pinned branch" in text:
        return "recoverable_source", "native_worker_verify_rollback_interruption_or_escalate"
    if "invalid exact source symbol" in text:
        return "recoverable_source", "native_worker_verify_symbol_parser_upgrade_or_escalate"
    if "source path not authorized" in text:
        return "recoverable_source", "native_worker_retry_authorized_source_discovery_or_escalate"
    if "invalid source search" in text:
        return "recoverable_source", "native_worker_verify_search_shape_upgrade_or_escalate"
    if "source evidence turn budget exhausted" in text:
        return "recoverable_source", "native_worker_verify_source_upgrade_or_escalate"
    if any(term in text for term in ("source excerpt", "source context", "source-code context",
                                      "unseen code", "repository excerpt", "missing exact source")):
        return "recoverable_source", "native_worker_read_only_evidence_turn"
    if any(term in text for term in ("http transport failed", "connectortransporterror",
                                      "provider_timeout", "connection reset")):
        return "recoverable_transport", "native_worker_verify_provider_then_readmit"
    if any(term in text for term in ("regression test", "ci failure", "exact repair anchor")):
        return "recoverable_validation", "native_worker_review_tests_or_exact_anchors"
    return "needs_triage", "inspect_bounded_state_evidence"


def build_snapshot(spool: Path, prior: Mapping[str, Any] | None = None) -> dict[str, Any]:
    for required in ("state.json", "development-state.json", "todo-intake-state.json"):
        if not (spool / required).is_file():
            raise ValueError("required supervisor evidence unavailable")
    support = load(spool, "state.json")
    development = load(spool, "development-state.json")
    intake = load(spool, "todo-intake-state.json")
    objects: list[dict[str, str]] = []
    no_longer_open = set(
        (support.get("support_state_mismatches") or {}).get("support_open_issue_not_open") or []
    )

    for lane, data in (("support", support), ("development", development)):
        records = data.get("items", {})
        if not isinstance(records, Mapping):
            raise ValueError("invalid supervisor work inventory")
        for identifier, record in records.items():
            if (not isinstance(identifier, str) or
                    not re.fullmatch(r"(?:SUPPORT-[A-Z]+-[0-9]+|SUPPORT-AUTO-[A-F0-9]{12}|DEV-[1-9][0-9]*)",
                                     identifier) or not isinstance(record, Mapping)):
                continue
            if lane == "support" and identifier in no_longer_open:
                continue
            phase = str(record.get("phase") or "unknown")[:55]
            category, next_action = classify(phase, str(record.get("reason") or ""), lane=lane)
            if category == "complete":
                continue
            progress = {
                field: str(record.get(field) or "")
                for field in ("phase", "reasoning_request_id", "pr_number",
                              "merge_sha", "acceptance_request_id",
                              "evidence_turn_count", "source_context_recovery_request_id")
            }
            progress_digest = hashlib.sha256(
                json.dumps(progress, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            objects.append({
                "id": identifier, "lane": lane, "phase": phase,
                "category": category, "next_action": next_action,
                "progress_sha256": progress_digest,
            })

    items = (intake.get("downstream_commitments") or {}).get("items") or []
    if not isinstance(items, list):
        raise ValueError("invalid approved commitment inventory")
    for item in items:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id") or "")
        if not re.fullmatch(r"TODO-[A-Z]+-[0-9]+", identifier):
            continue
        category, next_action = classify(
            str(item.get("phase") or ""), str(item.get("reason") or ""), lane="approved_todo",
        )
        objects.append({
            "id": identifier, "lane": "approved_todo",
            "phase": str(item.get("phase") or "")[:55],
            "category": category, "next_action": next_action,
        })

    objects.sort(key=lambda row: (row["lane"], row["id"]))
    # Hash only normalized non-sensitive work disposition fields. This is a
    # durable change detector, not a record of private provider output.
    fingerprint = hashlib.sha256(json.dumps(objects, sort_keys=True).encode()).hexdigest()
    prior = prior if isinstance(prior, Mapping) else {}
    previous_fingerprint = prior.get("disposition_sha256")
    no_progress = (min(int(prior.get("unchanged_cycles") or 0) + 1, 288)
                   if fingerprint == previous_fingerprint else 0)
    counts: dict[str, int] = {}
    for row in objects:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    active = int(intake.get("active_development_items") or 0) + int(intake.get("active_support_repairs") or 0)
    outstanding = int((intake.get("downstream_commitments") or {}).get("outstanding_count") or 0)
    capacity = int(intake.get("engineering_capacity") or 0)
    stalled = outstanding > 0 and active == 0 and capacity > 0
    internal = sum(counts.get(name, 0) for name in (
        "recoverable_source", "recoverable_transport", "recoverable_validation",
        "recoverable_credit", "needs_triage"))
    blocker = ("internal_recovery_needed" if stalled and internal
               else "external_or_governed_gate" if stalled else None)
    return {
        "schema_version": "1.0", "observed_at": now(),
        "status": "degraded" if stalled else "healthy",
        "reason": blocker,
        "active": active, "engineering_capacity": capacity, "approved_outstanding": outstanding,
        "unchanged_cycles": no_progress,
        "disposition_sha256": fingerprint,
        "category_counts": counts,
        "items": objects[:150],
        "items_truncated": len(objects) > 150,
        "action_owner": "existing_governed_worker_or_verified_human",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    args = parser.parse_args()
    path = args.spool.resolve() / "engineering-supervisor-state.json"
    try:
        prior = load(args.spool.resolve(), path.name)
        snapshot = build_snapshot(args.spool.resolve(), prior)
        atomic_write(path, snapshot)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # A broken supervisor cannot assert that blocked work became healthy.
        print("ENGINEERING_SUPERVISOR=FAILED " + type(exc).__name__, flush=True)
        return 1
    print("ENGINEERING_SUPERVISOR=" + snapshot["status"]
          + " reason=" + str(snapshot["reason"])
          + " outstanding=" + str(snapshot["approved_outstanding"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
