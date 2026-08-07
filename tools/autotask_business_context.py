#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys
from typing import Sequence
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
CLI_SOURCE = IMPLEMENTATION_ROOT / "cli" / "src"
CAP003_SOURCE = IMPLEMENTATION_ROOT / "cap-003" / "src"
CAP001_SOURCE = IMPLEMENTATION_ROOT / "cap-001" / "src"

for source in (
    IMPLEMENTATION_ROOT,
    CLI_SOURCE,
    CAP003_SOURCE,
    CAP001_SOURCE,
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from jason_cap_001.secret_provider_readiness import require_deployment_ready
from jason_cap_003.runtime import (
    CAPABILITY_NAME,
    build_autotask_business_context_runtime,
)
from jason_cli.runtime import build_autotask_connector
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator import OrchestrationMode, OrchestrationRequest

DEFAULT_DEPLOYMENT_RECORD = Path(
    "07-Operations/Jason-Secret-Provider-Deployment-Record.md"
)
DEFAULT_EVIDENCE_ROOT = Path.home() / "Jason-Evidence" / "Autotask-Business-Context"
DEFAULT_EVENT_STORE = (
    Path.home() / "Jason-Evidence" / "Orchestrator" / "orchestration.sqlite3"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build governed Autotask business context for one company and produce "
            "a local Jason operational briefing."
        )
    )
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--execution-id")
    parser.add_argument("--correlation-id")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--event-store", type=Path, default=DEFAULT_EVENT_STORE)
    parser.add_argument(
        "--deployment-record",
        type=Path,
        default=DEFAULT_DEPLOYMENT_RECORD,
    )
    parser.add_argument("--check-only", action="store_true")
    return parser


def run(args: argparse.Namespace):
    values = {
        "company-name": args.company_name,
        "principal-id": args.principal_id,
        "organization-id": args.organization_id,
    }
    missing = sorted(
        name for name, value in values.items() if not str(value).strip()
    )
    if missing:
        raise ValueError("Required values are blank: " + ", ".join(missing))

    execution_id = (args.execution_id or f"autotask-context-{uuid4()}").strip()
    correlation_id = (args.correlation_id or f"corr-{uuid4()}").strip()
    evidence_root = args.evidence_root.expanduser().resolve()
    event_store = args.event_store.expanduser().resolve()

    if not args.check_only:
        require_deployment_ready(args.deployment_record)
    else:
        event_store = Path(":memory:")

    runtime = build_autotask_business_context_runtime(
        autotask_connector=build_autotask_connector(),
        event_store_path=event_store,
        repository_root=REPOSITORY_ROOT,
    )
    try:
        result = runtime.orchestrator.execute(
            OrchestrationRequest(
                execution_id=execution_id,
                correlation_id=correlation_id,
                principal_id=args.principal_id.strip(),
                organization_id=args.organization_id.strip(),
                capability_name=CAPABILITY_NAME,
                capability_version=None,
                requested_mode="local_ai",
                orchestration_mode=(
                    OrchestrationMode.CHECK_ONLY
                    if args.check_only
                    else OrchestrationMode.EXECUTE
                ),
                authority_allowed=True,
                approval_present=False,
                risk="low",
                data_handling=DataHandlingPolicy(
                    classification="internal",
                    hosted_processing_allowed=False,
                    retention_allowed=True,
                ),
                budget=ExecutionBudget(
                    maximum_estimated_cost=Decimal("0"),
                    maximum_input_tokens=16384,
                    maximum_output_tokens=3072,
                    maximum_attempts=1,
                ),
                arguments={
                    "company_name": args.company_name.strip(),
                    "evidence_directory": str(evidence_root),
                },
                requester_kind="human",
                allow_pilot_capability=True,
                allow_pilot_provider=True,
            )
        )
        events = runtime.event_store.list_by_execution(execution_id)
    finally:
        runtime.close()
    return result, events


def _failure_detail(events) -> str:
    if not events:
        return "No orchestration events were recorded."
    last = events[-1]
    error_code = last.payload.get("error_code")
    if error_code:
        return f"Last event: {last.event_type}; error_code={error_code}"
    return f"Last event: {last.event_type}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result, events = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")

    print(f"Status: {result.status.value}")
    print(f"Execution ID: {result.execution_id}")
    print(f"Correlation ID: {result.correlation_id}")
    print(f"Capability: {result.capability_name}")

    if args.check_only:
        print("Capability invoked: false")
        print(
            "APPROVED: Autotask business-context request resolved through governance; "
            "no Autotask or local-LLM request was made."
        )
        return 0

    if result.status.value != "succeeded":
        print(f"Failure detail: {_failure_detail(events)}", file=sys.stderr)
        parser.exit(
            1,
            "DENIED: Governed Autotask business-context execution did not succeed.\n",
        )

    output = result.output
    print(f"Company: {output['company_name']}")
    print(f"Discovered Autotask company ID: {output['company_id']}")
    print(f"Local model: {output['model']}")
    print(f"Confidence: {output['confidence']}")
    print()
    print("Record counts:")
    for name, count in output["record_counts"].items():
        print(f"- {name}: {count}")
    print()
    print("Executive summary:")
    print(output["executive_summary"])
    print()
    print("Operational observations:")
    for item in output["operational_observations"]:
        print(f"- {item}")
    print()
    print("Service risks:")
    for item in output["service_risks"]:
        print(f"- {item}")
    print()
    print("Recommended focus:")
    for item in output["recommended_focus"]:
        print(f"- {item}")
    if output["notable_relationships"]:
        print()
        print("Notable relationships:")
        for item in output["notable_relationships"]:
            print(f"- {item}")
    print()
    print("Provider-side change: false")
    print("Artifacts:")
    for artifact in result.artifact_references:
        print(f"- {artifact.reference}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
