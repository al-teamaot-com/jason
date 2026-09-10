#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
RUNTIME_SOURCE = IMPLEMENTATION_ROOT / "runtime_service" / "src"
CAP007_SOURCE = IMPLEMENTATION_ROOT / "cap-007" / "src"
TOOLS_ROOT = REPOSITORY_ROOT / "tools"

for source in (
    IMPLEMENTATION_ROOT,
    RUNTIME_SOURCE,
    CAP007_SOURCE,
    TOOLS_ROOT,
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

import provider_cross_correlation_live_acceptance as correlation_live
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    SERVICE_TICKET_SEARCH,
)
from orchestrator.real_record_correlation_acceptance import stable_payload_sha256
from orchestrator.real_record_correlation_sample import (
    select_autotask_ticket_sample,
)


MAXIMUM_SAMPLE_RECORDS = 25


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select one deterministic ticket from a bounded real Autotask sample, "
            "prefer a ticket carrying an endpoint relationship, and run the existing "
            "cross-provider correlation acceptance without printing or persisting the "
            "selected ticket number or raw provider records."
        )
    )
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--client-id")
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument(
        "--openbao-url",
        default=correlation_live.DEFAULT_OPENBAO_URL,
    )
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def _validate(args: argparse.Namespace) -> Path:
    if args.check_only == args.live_read:
        raise PermissionError(
            "Choose exactly one mode: --check-only or explicit --live-read."
        )
    for name in (
        "principal_id",
        "organization_id",
        "correlation_id",
        "openbao_url",
    ):
        if not str(getattr(args, name) or "").strip():
            raise ValueError(f"{name.replace('_', '-')} must not be blank")

    target = args.evidence_output.expanduser().resolve()
    if target.exists():
        raise FileExistsError("Evidence output already exists; overwrite is denied.")
    try:
        target.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return target
    raise ValueError("Correlation evidence must be written outside the repository.")


def _sample_items(output: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError(
            "Autotask sample did not contain the governed data envelope"
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Autotask sample did not contain its item collection")
    if len(items) > MAXIMUM_SAMPLE_RECORDS:
        raise RuntimeError("Autotask sample exceeded its bounded record limit")
    if not all(isinstance(item, Mapping) for item in items):
        raise RuntimeError("Autotask sample contained a malformed ticket")
    return items


def _cross_provider_proof_count(payload: Mapping[str, Any]) -> int:
    stages = payload.get("stages")
    if not isinstance(stages, list):
        return 0
    count = 0
    for stage in stages:
        if not isinstance(stage, Mapping):
            continue
        providers = stage.get("provider_ids")
        if (
            str(stage.get("status", "")).strip().casefold() == "proven"
            and isinstance(providers, list)
            and len({str(item) for item in providers if str(item).strip()}) >= 2
        ):
            count += 1
    return count


def _rewrite_sanitized_evidence(
    destination: Path,
    payload: Mapping[str, Any],
) -> None:
    temporary = destination.with_suffix(destination.suffix + ".sample.tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def run(args: argparse.Namespace) -> Path | None:
    destination = _validate(args)

    if args.check_only:
        print(
            json.dumps(
                {
                    "seed_provider": "autotask",
                    "sample_maximum_records": MAXIMUM_SAMPLE_RECORDS,
                    "selection_prefers_configuration_link": True,
                    "selection_uses_first_provider_result": False,
                    "selected_ticket_identifier_persisted": False,
                    "selected_ticket_identifier_printed": False,
                    "peer_providers": ["it_glue", "datto_rmm"],
                    "raw_provider_payload_persisted": False,
                    "raw_provider_payload_printed": False,
                    "hosted_model_used": False,
                    "network_contacted": False,
                    "durable_activation_mutated": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return None

    sample_audit = correlation_live.SanitizedAudit()
    sample_orchestrator = correlation_live._build_orchestrator(args, sample_audit)
    sample_result = correlation_live._execute(
        sample_orchestrator,
        args,
        SERVICE_TICKET_SEARCH,
        {"page_size": MAXIMUM_SAMPLE_RECORDS},
        AUTOTASK_PROVIDER,
    )
    if sample_result.resolution is None or sample_result.resolution.execution_plan is None:
        raise RuntimeError("Autotask sample did not produce a governed execution plan")
    sample_plan = sample_result.resolution.execution_plan
    if (
        sample_plan.model_id is not None
        or sample_plan.estimated_cost.total_estimated_cost != Decimal("0")
    ):
        raise RuntimeError(
            "Autotask sampling unexpectedly selected a hosted model or billable path"
        )

    selection = select_autotask_ticket_sample(
        _sample_items(sample_result.output),
        maximum_records=MAXIMUM_SAMPLE_RECORDS,
    )
    sample_response_sha256 = stable_payload_sha256(sample_result.output)

    exact_args = argparse.Namespace(
        ticket_number=selection.ticket_number,
        principal_id=args.principal_id,
        organization_id=args.organization_id,
        client_id=args.client_id,
        correlation_id=args.correlation_id,
        evidence_output=destination,
        openbao_url=args.openbao_url,
        live_read=True,
        check_only=False,
    )
    output = correlation_live.run(exact_args)
    if output is None:
        raise RuntimeError("Cross-provider correlation acceptance produced no evidence")

    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Correlation acceptance evidence has an invalid shape")

    previous_package_hash = str(payload.pop("package_sha256", "")).strip()
    payload["acceptance_sampling"] = {
        **dict(selection.sanitized_metadata()),
        "sample_maximum_records": MAXIMUM_SAMPLE_RECORDS,
        "sample_response_sha256": sample_response_sha256,
        "sample_provider": "autotask",
        "sample_capability": SERVICE_TICKET_SEARCH,
        "sample_connector_events": sample_audit.connector_events,
        "sample_orchestration_events": sample_audit.orchestration_events,
        "selected_ticket_identifier_persisted": False,
        "selected_ticket_identifier_printed": False,
        "raw_provider_payload_persisted": False,
        "hosted_model_used": False,
        "hosted_model_cost_usd": "0",
    }
    proof_count = _cross_provider_proof_count(payload)
    payload["cross_provider_proven_stage_count"] = proof_count
    payload["prior_package_sha256"] = previous_package_hash or None
    payload["package_sha256"] = stable_payload_sha256(payload)

    if proof_count < 1:
        payload["status"] = "not_proven"
        payload.pop("package_sha256", None)
        payload["package_sha256"] = stable_payload_sha256(payload)
        _rewrite_sanitized_evidence(destination, payload)
        raise RuntimeError(
            "bounded real-record sample completed safely but did not prove an "
            "unambiguous cross-provider mapping; sanitized evidence was retained"
        )

    payload["status"] = "pass"
    payload.pop("package_sha256", None)
    payload["package_sha256"] = stable_payload_sha256(payload)
    _rewrite_sanitized_evidence(destination, payload)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    if args.live_read:
        print("PASS: bounded sampled real-record cross-provider proof completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
