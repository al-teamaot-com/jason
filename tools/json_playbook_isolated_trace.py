"""Synthetic JSON playbook trace utility.

Reuses Jason's existing schema, validator, and interpreter. This utility is
NOT a second runbook engine, a provider executor, a registry, or an authority
grant. It does not import provider clients, accept live secrets, or stage or
activate JSON. Its only output is a trace of *proposed* instructions on fixed
synthetic facts.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from implementation.autonomous_remediation.playbook_document import (
    PlaybookDocument, validate_playbook_document,
)
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter


def trace_synthetic(document: PlaybookDocument, *, facts: Mapping[str, Any],
                    max_steps: int = 200) -> dict[str, Any]:
    if document.autonomy_activation != "shadow":
        raise PermissionError("MIGRATION_SHADOW_ONLY")
    if document.payload.get("scope", {}).get("direct_provider_access") is not False:
        raise PermissionError("MIGRATION_DIRECT_PROVIDER_ACCESS_FORBIDDEN")
    if not 1 <= max_steps <= 200:
        raise ValueError("MIGRATION_STEP_LIMIT_INVALID")
    runtime = JsonPlaybookInterpreter(document)
    current = document.entry_step
    instructions: list[dict[str, Any]] = []
    for _ in range(max_steps):
        step = runtime.instruction(step_id=current, facts=facts)
        record = asdict(step)
        record["execution_status"] = "proposed_only_no_provider_call"
        instructions.append(record)
        if step.terminal:
            return {
                "mode": "synthetic_shadow_trace",
                "playbook_id": document.playbook_id,
                "version": document.version,
                "fingerprint": document.fingerprint,
                "facts_sha256": sha256(
                    json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "terminal_step": step.step_id,
                "instructions": instructions,
                "provider_calls": 0,
                "provider_mutations": 0,
                "authority_granted": False,
                "operational_acceptance": False,
            }
        nxt = runtime.next_step(step.step_id, facts=facts)
        if nxt is None:
            raise RuntimeError("MIGRATION_MISSING_NONTERMINAL_NEXT")
        current = nxt
    raise RuntimeError("MIGRATION_SHADOW_TRACE_STEP_LIMIT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    doc = validate_playbook_document(json.loads(args.candidate.read_text()))
    facts = json.loads(args.fixture.read_text())
    if not isinstance(facts, dict):
        raise ValueError("MIGRATION_FIXTURE_FACTS_OBJECT_REQUIRED")
    out = trace_synthetic(doc, facts=facts)
    data = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
        print(args.output)
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
