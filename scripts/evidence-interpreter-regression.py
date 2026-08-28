#!/usr/bin/env python3
"""Run the generic evidence interpreter against one saved evidence bundle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from orchestrator.authoritative_derivations import AuthoritativeDerivationRegistry
from orchestrator.evidence_interpreter import EvidenceVerifier
from orchestrator.evidence_regressions import WORKSTATION_EVIDENCE_REGRESSIONS
from orchestrator.generic_evidence_reasoning import (
    GenericStructuredEvidenceReasoner,
    GovernedEvidenceInterpreter,
)
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run many unrelated workstation questions through one generic, "
            "governed evidence interpreter and one saved evidence bundle."
        )
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("JASON_OLLAMA_URL", "http://jason-ollama:11434"),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("JASON_OLLAMA_MODEL", ""),
    )
    parser.add_argument("--max-catalog-entries", type=int, default=4000)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def compact_value(value):
    rendered = json.dumps(value, sort_keys=True, default=str)
    if len(rendered) <= 500:
        return value
    return rendered[:497] + "..."


def main() -> int:
    args = parse_args()
    if not args.model.strip():
        print("ERROR: --model or JASON_OLLAMA_MODEL is required", file=sys.stderr)
        return 2
    if not args.fixture.is_file():
        print(f"ERROR: fixture does not exist: {args.fixture}", file=sys.stderr)
        return 2

    with args.fixture.open("r", encoding="utf-8") as handle:
        evidence_bundle = json.load(handle)
    if not isinstance(evidence_bundle, dict):
        print("ERROR: fixture root must be a JSON object", file=sys.stderr)
        return 2

    derivations = AuthoritativeDerivationRegistry()
    verifier = EvidenceVerifier(approved_derivations=derivations.names)
    client = OllamaStructuredJsonClient(
        transport=UrlLibJsonHttpTransport(),
        model=args.model,
        base_url=args.ollama_url,
    )
    reasoner = GenericStructuredEvidenceReasoner(
        client=client,
        approved_derivations=derivations.names,
    )
    interpreter = GovernedEvidenceInterpreter(
        reasoner=reasoner,
        verifier=verifier,
        derivations=derivations,
        max_catalog_entries=args.max_catalog_entries,
    )

    failures = 0
    results = []

    for index, case in enumerate(WORKSTATION_EVIDENCE_REGRESSIONS, start=1):
        record = {
            "index": index,
            "name": case.name,
            "question": case.question,
            "expectation": case.expectation,
        }
        try:
            interpretation = interpreter.interpret(
                question=case.question,
                evidence_bundle=evidence_bundle,
            )
            paths = [item.path for item in interpretation.verified.evidence]
            values = [compact_value(item.value) for item in interpretation.verified.evidence]
            lowered_paths = "\n".join(paths).casefold()
            forbidden_hits = [
                term
                for term in case.forbidden_path_terms
                if term.casefold() in lowered_paths
            ]

            passed = True
            reasons = []
            if (
                case.expectation == "supported"
                and interpretation.verified.answer_type == "unavailable"
            ):
                passed = False
                reasons.append("required evidence was not located")
            if forbidden_hits:
                passed = False
                reasons.append(
                    "known-dangerous semantic substitution selected: "
                    + ", ".join(forbidden_hits)
                )

            record.update(
                {
                    "status": "PASS" if passed else "FAIL",
                    "answer_type": interpretation.verified.answer_type,
                    "evidence_paths": paths,
                    "verified_values": values,
                    "derived_value": (
                        interpretation.derived.value
                        if interpretation.derived is not None
                        else None
                    ),
                    "reasons": reasons,
                }
            )
            if not passed:
                failures += 1
        except Exception as exc:  # regression runner must continue all cases
            failures += 1
            record.update(
                {
                    "status": "ERROR",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

        results.append(record)
        answer_type = record.get("answer_type", "error")
        print(
            f"[{index:02d}] {record['status']:<5} {case.name:<28} "
            f"answer_type={answer_type}"
        )
        if record.get("reasons"):
            for reason in record["reasons"]:
                print(f"     reason: {reason}")
        if record.get("error"):
            print(f"     error: {record['error_type']}: {record['error']}")
        for path in record.get("evidence_paths", []):
            print(f"     evidence: {path}")
        if record.get("derived_value") is not None:
            print(f"     derived: {record['derived_value']}")

    summary = {
        "fixture": str(args.fixture),
        "model": args.model,
        "ollama_url": args.ollama_url,
        "total": len(results),
        "passed": len(results) - failures,
        "failed": failures,
        "results": results,
    }

    print()
    print(
        "REGRESSION_SUMMARY="
        f"{summary['passed']}/{summary['total']} passed; "
        f"{summary['failed']} failed"
    )

    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        with args.json_output.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        print(f"JSON_OUTPUT={args.json_output}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
