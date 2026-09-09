#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
RUNTIME_SOURCE = IMPLEMENTATION_ROOT / "runtime_service" / "src"
CAP007_SOURCE = IMPLEMENTATION_ROOT / "cap-007" / "src"

for source in (IMPLEMENTATION_ROOT, RUNTIME_SOURCE, CAP007_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from jason_runtime.provider_reads import build_provider_read_invoker
from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_policy import (
    CostEstimator,
    DataHandlingPolicy,
    ExecutionBudget,
    ExecutionPolicyEngine,
    InMemoryPricingRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from kernel.resolution import GovernedCapabilityResolutionEngine
from orchestrator.contracts import (
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationStatus,
)
from orchestrator.provider_read_acceptance import (
    ProviderReadAcceptanceRecord,
    build_provider_read_activation_plan,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)
from orchestrator.service import CentralOrchestrator


DEFAULT_OPENBAO_URL = "http://127.0.0.1:8200"
_PROVIDER_CONFIG = {
    IT_GLUE_PROVIDER: {
        "canonical_capability": DOCUMENTATION_ORGANIZATION_SEARCH,
        "provider_capability": "it_glue.entity.query",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle"
        ),
        "selector_argument": "name",
        "selector_flag": "organization-name",
    },
    AUTOTASK_PROVIDER: {
        "canonical_capability": SERVICE_TICKET_SEARCH,
        "provider_capability": "autotask.ticket.search",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/autotask-read-approle"
        ),
        "selector_argument": "ticket_number",
        "selector_flag": "ticket-number",
    },
}


class SanitizedAcceptanceAudit:
    """Collect event names only; never persist connector details or provider payloads."""

    def __init__(self) -> None:
        self.connector_events: list[str] = []
        self.orchestration_events: list[str] = []

    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        del context, details
        self.connector_events.append(event_type)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        del payload
        self.orchestration_events.append(event_type)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded provider-backed acceptance read through Jason's Central "
            "Orchestrator without printing credentials or raw provider records."
        )
    )
    parser.add_argument(
        "--provider",
        choices=tuple(sorted(_PROVIDER_CONFIG)),
        required=True,
    )
    parser.add_argument("--organization-name")
    parser.add_argument("--ticket-number")
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--client-id")
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--openbao-url", default=DEFAULT_OPENBAO_URL)
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def _selector(args: argparse.Namespace) -> tuple[str, str]:
    config = _PROVIDER_CONFIG[args.provider]
    if args.provider == IT_GLUE_PROVIDER:
        value = str(args.organization_name or "").strip()
        wrong = str(args.ticket_number or "").strip()
    else:
        value = str(args.ticket_number or "").strip()
        wrong = str(args.organization_name or "").strip()
    if not value:
        raise ValueError(f"--{config['selector_flag']} is required for {args.provider}")
    if wrong:
        raise ValueError("Only the selector for the chosen provider may be supplied")
    return str(config["selector_argument"]), value


def _validate_destination(destination: Path) -> Path:
    target = destination.expanduser().resolve()
    if target.exists():
        raise FileExistsError("Evidence output already exists; overwrite is denied.")
    root = REPOSITORY_ROOT.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("Provider acceptance evidence must be written outside the repository.")
    return target


def validate_configuration(args: argparse.Namespace) -> tuple[Path, str, str]:
    if args.check_only == args.live_read:
        raise PermissionError(
            "Choose exactly one mode: --check-only or explicit --live-read."
        )
    required = {
        "principal-id": args.principal_id,
        "organization-id": args.organization_id,
        "correlation-id": args.correlation_id,
        "openbao-url": args.openbao_url,
    }
    missing = sorted(name for name, value in required.items() if not str(value).strip())
    if missing:
        raise ValueError("Required values are blank: " + ", ".join(missing))
    selector_argument, selector_value = _selector(args)
    return _validate_destination(args.evidence_output), selector_argument, selector_value


def _foundation():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    return capabilities, providers


def _prepare_ephemeral_acceptance_probe(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    provider_id: str,
    capability_name: str,
) -> None:
    """Permit one in-process probe without changing deployed or durable state.

    Source defaults remain PILOT/PLANNED. This temporary registry state exists only
    because provider-backed evidence cannot be collected while a PLANNED provider is
    ineligible for selection. The resulting evidence is evaluated separately and no
    activation state is persisted by this harness.
    """

    providers.set_health(provider_id=provider_id, health_status=ProviderHealth.HEALTHY)
    providers.set_approval(
        provider_id=provider_id,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_lifecycle(
        provider_id=provider_id,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    capabilities.set_lifecycle(
        capability_name=capability_name,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )


def _build_orchestrator(
    *,
    provider_id: str,
    audit: SanitizedAcceptanceAudit,
    openbao_url: str,
) -> CentralOrchestrator:
    capabilities, providers = _foundation()
    config = _PROVIDER_CONFIG[provider_id]
    capability_name = str(config["canonical_capability"])
    _prepare_ephemeral_acceptance_probe(
        capabilities=capabilities,
        providers=providers,
        provider_id=provider_id,
        capability_name=capability_name,
    )

    credential_dir = Path(config["credential_dir"])
    resolver = OpenBaoSecretResolver(
        base_url=openbao_url.strip(),
        role_id_path=credential_dir / "role-id",
        secret_id_path=credential_dir / "secret-id",
    )
    invoker = build_provider_read_invoker(
        secrets=resolver,
        transport=UrlLibJsonHttpTransport(),
        audit=audit,
    )
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=ExecutionPolicyEngine(
            cost_estimator=CostEstimator(InMemoryPricingRegistry())
        ),
    )
    return CentralOrchestrator(
        resolution=resolution,
        invoker=invoker,
        audit=audit,
    )


def _request(
    *,
    args: argparse.Namespace,
    selector_argument: str,
    selector_value: str,
) -> OrchestrationRequest:
    capability_name = str(_PROVIDER_CONFIG[args.provider]["canonical_capability"])
    return OrchestrationRequest(
        execution_id=f"provider-read-acceptance:{args.correlation_id.strip()}",
        correlation_id=args.correlation_id.strip(),
        principal_id=args.principal_id.strip(),
        organization_id=args.organization_id.strip(),
        client_id=(args.client_id.strip() if args.client_id and args.client_id.strip() else None),
        capability_name=capability_name,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        arguments={selector_argument: selector_value, "page_size": 1},
        permission_mode="observe",
    )


def _collection_count(provider_id: str, output: Mapping[str, Any]) -> int:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError("Provider result did not contain the governed data envelope.")
    key = "data" if provider_id == IT_GLUE_PROVIDER else "items"
    collection = data.get(key)
    if not isinstance(collection, list):
        raise RuntimeError("Provider response did not contain the expected collection.")
    if len(collection) > 1:
        raise RuntimeError("Provider returned more than the one-record acceptance bound.")
    return len(collection)


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _write_evidence(destination: Path, evidence: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(evidence), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def run(args: argparse.Namespace) -> Path | None:
    destination, selector_argument, selector_value = validate_configuration(args)
    config = _PROVIDER_CONFIG[args.provider]
    if args.check_only:
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "canonical_capability": config["canonical_capability"],
                    "provider_capability": config["provider_capability"],
                    "maximum_records": 1,
                    "network_contacted": False,
                    "provider_credentials_used": False,
                    "raw_provider_payload_persisted": False,
                    "hosted_model_used": False,
                    "durable_activation_mutated": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return None

    audit = SanitizedAcceptanceAudit()
    orchestrator = _build_orchestrator(
        provider_id=args.provider,
        audit=audit,
        openbao_url=args.openbao_url,
    )
    result = orchestrator.execute(
        _request(
            args=args,
            selector_argument=selector_argument,
            selector_value=selector_value,
        )
    )
    if result.status is not OrchestrationStatus.SUCCEEDED:
        raise RuntimeError(
            "Central Orchestrator provider-read acceptance did not succeed: "
            + ", ".join(result.reason_codes)
        )
    if result.provider_id != args.provider:
        raise RuntimeError("Resolved provider changed during acceptance.")
    if result.output.get("provider_capability") != config["provider_capability"]:
        raise RuntimeError("Resolved provider capability changed during acceptance.")
    if result.resolution is None or result.resolution.execution_plan is None:
        raise RuntimeError("Acceptance did not produce a governed execution plan.")
    if result.resolution.execution_plan.model_id is not None:
        raise RuntimeError("Acceptance unexpectedly selected a hosted model.")
    if result.resolution.execution_plan.estimated_cost.total_estimated_cost != Decimal("0"):
        raise RuntimeError("Acceptance unexpectedly selected a billable execution path.")

    count = _collection_count(args.provider, result.output)
    selector_sha256 = hashlib.sha256(selector_value.encode("utf-8")).hexdigest()
    response_sha256 = _sha256_json(result.output)
    observed_at = datetime.now(timezone.utc)
    evidence_reference = f"file://{destination}"
    acceptance = ProviderReadAcceptanceRecord(
        provider_id=args.provider,
        observed_at=observed_at,
        evidence_reference=evidence_reference,
        verified_capabilities=frozenset({str(config["canonical_capability"])}),
        status="pass",
        provider_backed=True,
        read_only=True,
        credential_boundary_proven=True,
        protected_values_exposed=False,
        raw_provider_payload_persisted=False,
        hosted_model_used=False,
    )
    activation_plan = build_provider_read_activation_plan(acceptance)

    evidence = {
        "schema_version": "1.0",
        "provider": args.provider,
        "canonical_capability": config["canonical_capability"],
        "provider_capability": config["provider_capability"],
        "correlation_id": args.correlation_id.strip(),
        "observed_at": observed_at.isoformat(),
        "selector_kind": selector_argument,
        "selector_sha256": selector_sha256,
        "maximum_records": 1,
        "collection_count": count,
        "response_sha256": response_sha256,
        "provider_backed": True,
        "read_only": True,
        "credential_boundary": "OpenBao logical secret resolver",
        "credential_boundary_proven": True,
        "provider_credentials_printed": False,
        "raw_provider_payload_persisted": False,
        "raw_provider_payload_printed": False,
        "hosted_model_used": False,
        "durable_activation_mutated": False,
        "connector_events": audit.connector_events,
        "orchestration_events": audit.orchestration_events,
        "activation_plan": asdict(activation_plan),
        "status": "pass",
    }
    _write_evidence(destination, evidence)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")

    if args.live_read:
        print("PASS: Central Orchestrator provider-read acceptance completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
