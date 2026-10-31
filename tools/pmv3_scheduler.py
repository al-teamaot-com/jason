#!/usr/bin/env python3
"""Persistent isolated PMV3 scheduler runner.

This runner intentionally has no production provider adapter. It persists PMV3
state, ingests bounded preproduction work/facts, executes one scheduler cycle,
and writes durable evidence. A future production adapter must implement the same
handler contract and Teams-only approval contract without changing engine
semantics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import pmv3_work_engine as engine


class SchedulerInputError(RuntimeError):
    pass


def load_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def ingest_work(state: dict[str, Any], path: Path) -> int:
    payload = load_json(path, default={"items": []})
    if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
        raise SchedulerInputError("invalid PMV3 work input")
    admitted = 0
    for raw in payload["items"]:
        if not isinstance(raw, Mapping):
            raise SchedulerInputError("invalid PMV3 work item")
        item = engine.make_item(
            str(raw.get("id") or ""),
            str(raw.get("action") or ""),
            priority=int(raw.get("priority") or 100),
            approved=bool(raw.get("approved", True)),
            dependency=str(raw.get("dependency") or ""),
            approval_required=bool(raw.get("approval_required", False)),
            approval_request_id=str(raw.get("approval_request_id") or ""),
        )
        if not item["action"]:
            raise SchedulerInputError("work item action required")
        admitted += int(engine.admit(state, item))
    return admitted


def ingest_teams_approvals(state: dict[str, Any], path: Path) -> int:
    payload = load_json(path, default={"approvals": []})
    if not isinstance(payload, Mapping) or not isinstance(payload.get("approvals"), list):
        raise SchedulerInputError("invalid PMV3 approval input")
    applied = 0
    for raw in payload["approvals"]:
        if not isinstance(raw, Mapping):
            raise SchedulerInputError("invalid PMV3 approval record")
        engine.record_teams_approval(
            state,
            str(raw.get("item_id") or ""),
            request_id=str(raw.get("request_id") or ""),
            decision=str(raw.get("decision") or ""),
            actor_id=str(raw.get("actor_id") or ""),
            tenant_id=str(raw.get("tenant_id") or ""),
            receipt_id=str(raw.get("receipt_id") or ""),
            verified=raw.get("verified") is True,
            channel=str(raw.get("channel") or ""),
        )
        applied += 1
    return applied


def load_facts(path: Path) -> dict[str, bool]:
    payload = load_json(path, default={})
    if not isinstance(payload, Mapping):
        raise SchedulerInputError("invalid PMV3 fact input")
    return {str(k): bool(v) for k, v in payload.items()}


def load_simulated_outcomes(path: Path) -> dict[str, list[dict[str, str]]]:
    """Preproduction-only deterministic handler input.

    This cannot authorize or call production providers. It lets the acceptance
    harness prove scheduler sequencing, retry/restart and idempotency.
    """
    payload = load_json(path, default={})
    if not isinstance(payload, Mapping):
        raise SchedulerInputError("invalid PMV3 simulated outcomes")
    result: dict[str, list[dict[str, str]]] = {}
    for item_id, values in payload.items():
        if not isinstance(values, list) or not all(isinstance(v, Mapping) for v in values):
            raise SchedulerInputError("invalid PMV3 outcome sequence")
        result[str(item_id)] = [dict(v) for v in values]
    return result


def simulation_handler(outcomes: dict[str, list[dict[str, str]]]):
    def handler(item: Mapping[str, Any], action_key: str) -> engine.Outcome:
        sequence = outcomes.get(str(item["id"])) or []
        index = max(0, int(item.get("attempts") or 1) - 1)
        if index >= len(sequence):
            return engine.Outcome("waiting", reason="simulation_outcome_unavailable", dependency="simulation_outcome")
        raw = sequence[index]
        return engine.Outcome(
            status=str(raw.get("status") or ""),
            reason=str(raw.get("reason") or ""),
            retry_class=str(raw.get("retry_class") or ""),
            dependency=str(raw.get("dependency") or ""),
            receipt=str(raw.get("receipt") or ""),
        )
    return handler


def snapshot(state: Mapping[str, Any], *, admitted: int, approvals: int) -> dict[str, Any]:
    return {
        "schema_version": engine.SCHEMA_VERSION,
        "cycle": int(state.get("cycle") or 0),
        "updated_at": state.get("updated_at"),
        "admitted_this_cycle": admitted,
        "teams_approvals_applied": approvals,
        "progress_percent": engine.progress_percent(state),
        "metrics": dict(state.get("metrics") or {}),
    }


def run_once(
    *,
    state_path: Path,
    work_path: Path,
    facts_path: Path,
    approvals_path: Path,
    outcomes_path: Path,
    status_path: Path,
    capacity: int,
) -> dict[str, Any]:
    state = engine.load_state(state_path)
    admitted = ingest_work(state, work_path)
    approvals = ingest_teams_approvals(state, approvals_path)
    facts = load_facts(facts_path)
    outcomes = load_simulated_outcomes(outcomes_path)

    engine.execute_cycle(
        state,
        facts=facts,
        handler=simulation_handler(outcomes),
        capacity=capacity,
    )
    engine.atomic_write(state_path, state)
    result = snapshot(state, admitted=admitted, approvals=approvals)
    engine.atomic_write(status_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--capacity", type=int, default=3)
    args = parser.parse_args()
    result = run_once(
        state_path=args.state,
        work_path=args.work,
        facts_path=args.facts,
        approvals_path=args.approvals,
        outcomes_path=args.outcomes,
        status_path=args.status,
        capacity=max(1, args.capacity),
    )
    print(
        "PMV3_SCHEDULER=OK"
        f" cycle={result['cycle']}"
        f" progress={result['progress_percent']}"
        f" metrics={json.dumps(result['metrics'], sort_keys=True)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
