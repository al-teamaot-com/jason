#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
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

for source in (IMPLEMENTATION_ROOT, RUNTIME_SOURCE, CAP007_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.core.relationships import ResourceRef, VerificationState
from connectors.core.resource_gateway import ResourceOperation, ResourceQuery
from connectors.datto_rmm.connector import DattoRmmConnector
from connectors.resource_convergence import GovernedResourceExecutor
from jason_runtime.provider_reads import build_provider_read_invoker
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
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
from orchestrator.canonical_entity_correlation import (
    CanonicalEntityCorrelationRegistry,
    CanonicalEntityMapping,
    CanonicalEntityType,
    CorrelationBasis,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest, OrchestrationStatus
from orchestrator.cross_provider_evidence import plan_correlated_resources
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_CONFIGURATION_READ,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)
from orchestrator.real_record_correlation_acceptance import (
    CorrelationAcceptanceError,
    RealRecordCorrelationAcceptance,
    collection_count,
    endpoint_matched_attributes,
    exact_name_match,
    extract_autotask_company_name,
    extract_autotask_endpoint_hint,
    extract_autotask_ticket_links,
    extract_it_glue_endpoint_hint,
    extract_it_glue_name,
    extract_it_glue_resource_id,
    require_single_autotask_item,
    require_single_it_glue_item,
    safe_stage,
    sha256_text,
    stable_payload_sha256,
)
from orchestrator.service import CentralOrchestrator


DEFAULT_OPENBAO_URL = "http://127.0.0.1:8200"
IT_GLUE_CREDENTIAL_DIR = Path("/opt/jason/bootstrap/secrets/openbao/itglue-read-approle")
AUTOTASK_CREDENTIAL_DIR = Path("/opt/jason/bootstrap/secrets/openbao/autotask-read-approle")
DATTO_RMM_CREDENTIAL_DIR = Path("/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle")

_REQUIRED_CAPABILITIES = (
    SERVICE_TICKET_SEARCH,
    SERVICE_COMPANY_READ,
    SERVICE_CONFIGURATION_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    DOCUMENTATION_CONFIGURATION_SEARCH,
)


class SanitizedAudit:
    """Retain event names only; raw provider records and connector details stay in memory."""

    def __init__(self) -> None:
        self.connector_events: list[str] = []
        self.orchestration_events: list[str] = []

    def record(self, event_type: str, context: ConnectorContext, details: Mapping[str, Any]) -> None:
        del context, details
        self.connector_events.append(event_type)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        del payload
        self.orchestration_events.append(event_type)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded, deterministic, real-record correlation proof from an "
            "Autotask ticket into IT Glue and, when the ticket supplies endpoint "
            "evidence, Datto RMM. Raw provider records are never printed or persisted."
        )
    )
    parser.add_argument("--ticket-number", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--client-id")
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--openbao-url", default=DEFAULT_OPENBAO_URL)
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def _validate_destination(destination: Path) -> Path:
    target = destination.expanduser().resolve()
    if target.exists():
        raise FileExistsError("Evidence output already exists; overwrite is denied.")
    try:
        target.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return target
    raise ValueError("Correlation evidence must be written outside the repository.")


def validate_configuration(args: argparse.Namespace) -> Path:
    if args.check_only == args.live_read:
        raise PermissionError("Choose exactly one mode: --check-only or explicit --live-read.")
    for name in ("ticket_number", "principal_id", "organization_id", "correlation_id", "openbao_url"):
        if not str(getattr(args, name) or "").strip():
            raise ValueError(f"{name.replace('_', '-')} must not be blank")
    return _validate_destination(args.evidence_output)


def _foundation():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        providers.set_health(provider_id=provider_id, health_status=ProviderHealth.HEALTHY)
        providers.set_approval(provider_id=provider_id, approval_status=ProviderApproval.APPROVED)
        providers.set_lifecycle(provider_id=provider_id, lifecycle_status=ProviderLifecycle.AVAILABLE)
    for capability_name in _REQUIRED_CAPABILITIES:
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    return capabilities, providers


def _resolver(base_url: str, credential_dir: Path) -> OpenBaoSecretResolver:
    return OpenBaoSecretResolver(
        base_url=base_url.strip(),
        role_id_path=credential_dir / "role-id",
        secret_id_path=credential_dir / "secret-id",
    )


def _build_orchestrator(args: argparse.Namespace, audit: SanitizedAudit) -> CentralOrchestrator:
    capabilities, providers = _foundation()
    invoker = build_provider_read_invoker(
        it_glue_secrets=_resolver(args.openbao_url, IT_GLUE_CREDENTIAL_DIR),
        autotask_secrets=_resolver(args.openbao_url, AUTOTASK_CREDENTIAL_DIR),
        transport=UrlLibJsonHttpTransport(),
        audit=audit,
    )
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=ExecutionPolicyEngine(cost_estimator=CostEstimator(InMemoryPricingRegistry())),
    )
    return CentralOrchestrator(resolution=resolution, invoker=invoker, audit=audit)


def _request(args: argparse.Namespace, capability_name: str, arguments: Mapping[str, Any]) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id=f"correlation-acceptance:{capability_name}:{args.correlation_id.strip()}",
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
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0"), maximum_attempts=1),
        arguments=dict(arguments),
        permission_mode="observe",
    )


def _execute(
    orchestrator: CentralOrchestrator,
    args: argparse.Namespace,
    capability_name: str,
    arguments: Mapping[str, Any],
    expected_provider: str,
):
    result = orchestrator.execute(_request(args, capability_name, arguments))
    if result.status is not OrchestrationStatus.SUCCEEDED:
        code = str(result.error_code or "CAPABILITY_INVOCATION_FAILED")
        raise RuntimeError(f"governed provider read failed safely: {code}")
    if result.provider_id != expected_provider:
        raise RuntimeError("governed resolution selected an unexpected provider")
    if result.resolution is None or result.resolution.execution_plan is None:
        raise RuntimeError("governed provider read did not produce an execution plan")
    plan = result.resolution.execution_plan
    if plan.model_id is not None or plan.estimated_cost.total_estimated_cost != Decimal("0"):
        raise RuntimeError("correlation acceptance unexpectedly selected a hosted model or billable path")
    return result


def _autotask_read_record(output: Mapping[str, Any]) -> Mapping[str, Any]:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise CorrelationAcceptanceError("Autotask exact read is missing the governed data envelope")
    # Autotask GET responses are provider objects. Retain compatibility with a
    # one-item envelope without ever selecting the first item from a larger set.
    items = data.get("items")
    if isinstance(items, list):
        if len(items) != 1 or not isinstance(items[0], Mapping):
            raise CorrelationAcceptanceError("Autotask exact read did not resolve exactly one object")
        return items[0]
    return data


def _mapping(
    *,
    canonical_id: str,
    entity_type: CanonicalEntityType,
    organization_id: str,
    provider: str,
    resource_type: str,
    external_id: str,
    basis: CorrelationBasis,
    confidence: float,
    provenance: tuple[str, ...],
    observed_at: datetime,
) -> CanonicalEntityMapping:
    verification = (
        VerificationState.VERIFIED
        if basis in {CorrelationBasis.CONFIGURED, CorrelationBasis.EXPLICIT}
        else VerificationState.CORROBORATED
    )
    return CanonicalEntityMapping(
        canonical_id=canonical_id,
        entity_type=entity_type,
        organization_id=organization_id,
        resource=ResourceRef(
            provider=provider,
            resource_type=resource_type,
            external_id=external_id,
            organization_id=organization_id,
        ),
        basis=basis,
        verification=verification,
        confidence=confidence,
        provenance=provenance,
        observed_at=observed_at,
    )


def _datto_discovery(
    args: argparse.Namespace,
    audit: SanitizedAudit,
    *,
    hostname: str,
) -> Mapping[str, Any]:
    connector = DattoRmmConnector(
        secrets=_resolver(args.openbao_url, DATTO_RMM_CREDENTIAL_DIR),
        transport=UrlLibJsonHttpTransport(),
        audit=audit,
    )
    executor = GovernedResourceExecutor(connectors={"datto_rmm": connector})
    query = ResourceQuery(
        provider="datto_rmm",
        resource_type="device",
        operation=ResourceOperation.QUERY,
        organization_id=args.organization_id.strip(),
        filters={"hostname": hostname},
        page_size=2,
    )
    result = executor.execute(
        query,
        ConnectorContext(
            correlation_id=args.correlation_id.strip(),
            principal_id=args.principal_id.strip(),
            organization_id=args.organization_id.strip(),
            client_id=(args.client_id.strip() if args.client_id and args.client_id.strip() else None),
            capability="provider-neutral.resource.query",
            mode="observe",
        ),
    )
    if result.provider != "datto_rmm" or result.capability != "datto_rmm.device.search":
        raise RuntimeError("Datto RMM convergence returned unexpected provider provenance")
    if not isinstance(result.data, Mapping):
        raise CorrelationAcceptanceError("Datto RMM discovery is missing its normalized envelope")
    return result.data


def _safe_datto_matches(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    matches = data.get("resource_matches")
    if not isinstance(matches, list) or not all(isinstance(item, Mapping) for item in matches):
        raise CorrelationAcceptanceError("Datto RMM discovery did not expose normalized resource matches")
    if len(matches) > 2:
        raise CorrelationAcceptanceError("Datto RMM exceeded the two-candidate acceptance bound")
    return list(matches)


def _write_evidence(destination: Path, payload: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def run(args: argparse.Namespace) -> Path | None:
    destination = validate_configuration(args)
    if args.check_only:
        print(
            json.dumps(
                {
                    "seed_provider": "autotask",
                    "peer_providers": ["it_glue", "datto_rmm"],
                    "ticket_search_maximum_records": 2,
                    "peer_search_maximum_records": 2,
                    "ambiguity_detection_enabled": True,
                    "exact_name_corroboration_required": True,
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

    audit = SanitizedAudit()
    orchestrator = _build_orchestrator(args, audit)
    observed_at = datetime.now(timezone.utc)
    stages = []
    read_hashes: list[dict[str, str]] = []
    mappings: list[CanonicalEntityMapping] = []

    ticket_result = _execute(
        orchestrator,
        args,
        SERVICE_TICKET_SEARCH,
        {"ticket_number": args.ticket_number.strip(), "page_size": 2},
        AUTOTASK_PROVIDER,
    )
    if collection_count(ticket_result.output, provider="autotask") != 1:
        count = collection_count(ticket_result.output, provider="autotask")
        raise CorrelationAcceptanceError(
            f"ticket selector did not resolve uniquely; candidate_count={count}"
        )
    ticket = require_single_autotask_item(ticket_result.output)
    links = extract_autotask_ticket_links(ticket)
    stages.append(
        safe_stage(
            stage="autotask_ticket_seed",
            candidate_count=1,
            provider_ids=("autotask",),
            resource_ids=(links.ticket_id,),
            matched_attributes=("ticket_number",),
        )
    )
    read_hashes.append(
        {
            "provider": "autotask",
            "capability": SERVICE_TICKET_SEARCH,
            "response_sha256": stable_payload_sha256(ticket_result.output),
        }
    )

    company_result = _execute(
        orchestrator,
        args,
        SERVICE_COMPANY_READ,
        {"resource_id": links.company_id},
        AUTOTASK_PROVIDER,
    )
    company = _autotask_read_record(company_result.output)
    company_name = extract_autotask_company_name(company)
    read_hashes.append(
        {
            "provider": "autotask",
            "capability": SERVICE_COMPANY_READ,
            "response_sha256": stable_payload_sha256(company_result.output),
        }
    )

    itg_org_result = _execute(
        orchestrator,
        args,
        DOCUMENTATION_ORGANIZATION_SEARCH,
        {"name": company_name, "page_size": 2},
        IT_GLUE_PROVIDER,
    )
    org_count = collection_count(itg_org_result.output, provider="it_glue")
    read_hashes.append(
        {
            "provider": "it_glue",
            "capability": DOCUMENTATION_ORGANIZATION_SEARCH,
            "response_sha256": stable_payload_sha256(itg_org_result.output),
        }
    )
    if org_count == 0:
        stages.append(
            safe_stage(
                stage="organization_correlation",
                candidate_count=0,
                provider_ids=("autotask", "it_glue"),
                matched_attributes=("name",),
                note="no IT Glue organization matched the provider-reported Autotask company name",
            )
        )
        itg_org_id = None
    elif org_count > 1:
        data = itg_org_result.output["data"]["data"]
        stages.append(
            safe_stage(
                stage="organization_correlation",
                candidate_count=org_count,
                provider_ids=("autotask", "it_glue"),
                resource_ids=tuple(item.get("id") for item in data if isinstance(item, Mapping) and item.get("id")),
                matched_attributes=("name",),
                note="multiple IT Glue organizations matched; no organization mapping selected",
            )
        )
        itg_org_id = None
    else:
        itg_org = require_single_it_glue_item(itg_org_result.output)
        itg_org_name = extract_it_glue_name(itg_org)
        if not exact_name_match(company_name, itg_org_name):
            raise CorrelationAcceptanceError("IT Glue organization candidate failed exact-name corroboration")
        itg_org_id = extract_it_glue_resource_id(itg_org)
        canonical_org_id = "acceptance-org:" + sha256_text(
            f"{args.ticket_number.strip()}|{links.company_id}|{itg_org_id}"
        )[:24]
        org_mappings = (
            _mapping(
                canonical_id=canonical_org_id,
                entity_type=CanonicalEntityType.ORGANIZATION,
                organization_id=args.organization_id.strip(),
                provider="autotask",
                resource_type="company",
                external_id=links.company_id,
                basis=CorrelationBasis.EXPLICIT,
                confidence=1.0,
                provenance=("autotask:ticket.companyID", "autotask:company.get"),
                observed_at=observed_at,
            ),
            _mapping(
                canonical_id=canonical_org_id,
                entity_type=CanonicalEntityType.ORGANIZATION,
                organization_id=args.organization_id.strip(),
                provider="it_glue",
                resource_type="organization",
                external_id=itg_org_id,
                basis=CorrelationBasis.CORROBORATED,
                confidence=0.95,
                provenance=("autotask:companyName", "it_glue:organization.name", "match:exact-normalized-name"),
                observed_at=observed_at,
            ),
        )
        registry = CanonicalEntityCorrelationRegistry(org_mappings)
        plan = plan_correlated_resources(
            seed=org_mappings[0].resource,
            entity_type=CanonicalEntityType.ORGANIZATION,
            registry=registry,
            target_providers=("it_glue",),
        )
        if {item.provider for item in plan.resources} != {"autotask", "it_glue"}:
            raise CorrelationAcceptanceError("canonical organization plan did not retain both providers")
        mappings.extend(plan.mappings)
        stages.append(
            safe_stage(
                stage="organization_correlation",
                candidate_count=1,
                provider_ids=("autotask", "it_glue"),
                resource_ids=(links.company_id, itg_org_id),
                matched_attributes=("name",),
            )
        )

    if not links.configuration_item_id:
        stages.append(
            safe_stage(
                stage="ticket_to_endpoint",
                candidate_count=0,
                provider_ids=("autotask",),
                not_applicable=True,
                note="ticket contains no governed configuration item reference",
            )
        )
    else:
        stages.append(
            safe_stage(
                stage="ticket_to_endpoint",
                candidate_count=1,
                provider_ids=("autotask",),
                resource_ids=(links.configuration_item_id,),
                matched_attributes=("ticket_configuration_reference",),
            )
        )
        config_result = _execute(
            orchestrator,
            args,
            SERVICE_CONFIGURATION_READ,
            {"resource_id": links.configuration_item_id},
            AUTOTASK_PROVIDER,
        )
        autotask_config = _autotask_read_record(config_result.output)
        at_hint = extract_autotask_endpoint_hint(autotask_config)
        read_hashes.append(
            {
                "provider": "autotask",
                "capability": SERVICE_CONFIGURATION_READ,
                "response_sha256": stable_payload_sha256(config_result.output),
            }
        )

        canonical_endpoint_id = "acceptance-endpoint:" + sha256_text(
            f"{args.ticket_number.strip()}|{links.configuration_item_id}"
        )[:24]
        endpoint_mappings = [
            _mapping(
                canonical_id=canonical_endpoint_id,
                entity_type=CanonicalEntityType.ENDPOINT,
                organization_id=args.organization_id.strip(),
                provider="autotask",
                resource_type="configuration_item",
                external_id=links.configuration_item_id,
                basis=CorrelationBasis.EXPLICIT,
                confidence=1.0,
                provenance=("autotask:ticket.configuration", "autotask:configuration.get"),
                observed_at=observed_at,
            )
        ]

        if itg_org_id is None:
            stages.append(
                safe_stage(
                    stage="it_glue_endpoint_correlation",
                    candidate_count=0,
                    provider_ids=("autotask", "it_glue"),
                    not_applicable=True,
                    note="endpoint search withheld because organization correlation was not unique",
                )
            )
        else:
            itg_config_result = _execute(
                orchestrator,
                args,
                DOCUMENTATION_CONFIGURATION_SEARCH,
                {
                    "filters": {"organization_id": itg_org_id, "name": at_hint.name},
                    "page_size": 2,
                },
                IT_GLUE_PROVIDER,
            )
            itg_config_count = collection_count(itg_config_result.output, provider="it_glue")
            read_hashes.append(
                {
                    "provider": "it_glue",
                    "capability": DOCUMENTATION_CONFIGURATION_SEARCH,
                    "response_sha256": stable_payload_sha256(itg_config_result.output),
                }
            )
            if itg_config_count == 0:
                stages.append(
                    safe_stage(
                        stage="it_glue_endpoint_correlation",
                        candidate_count=0,
                        provider_ids=("autotask", "it_glue"),
                        matched_attributes=("name",),
                        note="no IT Glue configuration matched the provider-reported Autotask configuration name",
                    )
                )
            elif itg_config_count > 1:
                data = itg_config_result.output["data"]["data"]
                stages.append(
                    safe_stage(
                        stage="it_glue_endpoint_correlation",
                        candidate_count=itg_config_count,
                        provider_ids=("autotask", "it_glue"),
                        resource_ids=tuple(item.get("id") for item in data if isinstance(item, Mapping) and item.get("id")),
                        matched_attributes=("name",),
                        note="multiple IT Glue configuration candidates matched; no endpoint mapping selected",
                    )
                )
            else:
                itg_config = require_single_it_glue_item(itg_config_result.output)
                itg_hint = extract_it_glue_endpoint_hint(itg_config)
                matched = endpoint_matched_attributes(at_hint, itg_hint)
                if "name" not in matched:
                    raise CorrelationAcceptanceError("IT Glue configuration candidate failed exact-name corroboration")
                itg_config_id = extract_it_glue_resource_id(itg_config)
                endpoint_mappings.append(
                    _mapping(
                        canonical_id=canonical_endpoint_id,
                        entity_type=CanonicalEntityType.ENDPOINT,
                        organization_id=args.organization_id.strip(),
                        provider="it_glue",
                        resource_type="configuration",
                        external_id=itg_config_id,
                        basis=CorrelationBasis.CORROBORATED,
                        confidence=(0.98 if "serial_number" in matched else 0.94),
                        provenance=tuple(
                            ["autotask:configuration.get", "it_glue:configuration.search"]
                            + [f"match:{item}" for item in matched]
                        ),
                        observed_at=observed_at,
                    )
                )
                stages.append(
                    safe_stage(
                        stage="it_glue_endpoint_correlation",
                        candidate_count=1,
                        provider_ids=("autotask", "it_glue"),
                        resource_ids=(links.configuration_item_id, itg_config_id),
                        matched_attributes=matched,
                    )
                )

        datto_data = _datto_discovery(args, audit, hostname=at_hint.name)
        datto_matches = _safe_datto_matches(datto_data)
        read_hashes.append(
            {
                "provider": "datto_rmm",
                "capability": "endpoint.device.search",
                "response_sha256": stable_payload_sha256(datto_data),
            }
        )
        if len(datto_matches) == 0:
            stages.append(
                safe_stage(
                    stage="datto_rmm_endpoint_correlation",
                    candidate_count=0,
                    provider_ids=("autotask", "datto_rmm"),
                    matched_attributes=("name",),
                    note="no Datto RMM device matched the Autotask configuration hostname",
                )
            )
        elif len(datto_matches) > 1:
            stages.append(
                safe_stage(
                    stage="datto_rmm_endpoint_correlation",
                    candidate_count=len(datto_matches),
                    provider_ids=("autotask", "datto_rmm"),
                    resource_ids=tuple(item.get("resource_id") for item in datto_matches if item.get("resource_id")),
                    matched_attributes=("name",),
                    note="multiple Datto RMM device candidates matched; no endpoint mapping selected",
                )
            )
        else:
            match = datto_matches[0]
            resource_id = str(match.get("resource_id") or "").strip()
            hostname = str(match.get("hostname") or "").strip()
            if not resource_id:
                raise CorrelationAcceptanceError("unique Datto RMM candidate lacked durable provider identity")
            if not exact_name_match(at_hint.name, hostname):
                raise CorrelationAcceptanceError("Datto RMM candidate failed exact-hostname corroboration")
            endpoint_mappings.append(
                _mapping(
                    canonical_id=canonical_endpoint_id,
                    entity_type=CanonicalEntityType.ENDPOINT,
                    organization_id=args.organization_id.strip(),
                    provider="datto_rmm",
                    resource_type="device",
                    external_id=resource_id,
                    basis=CorrelationBasis.CORROBORATED,
                    confidence=0.94,
                    provenance=("autotask:configuration.referenceTitle", "datto_rmm:device.hostname", "match:exact-normalized-name"),
                    observed_at=observed_at,
                )
            )
            stages.append(
                safe_stage(
                    stage="datto_rmm_endpoint_correlation",
                    candidate_count=1,
                    provider_ids=("autotask", "datto_rmm"),
                    resource_ids=(links.configuration_item_id, resource_id),
                    matched_attributes=("name",),
                )
            )

        endpoint_registry = CanonicalEntityCorrelationRegistry(endpoint_mappings)
        endpoint_plan = plan_correlated_resources(
            seed=endpoint_mappings[0].resource,
            entity_type=CanonicalEntityType.ENDPOINT,
            registry=endpoint_registry,
            target_providers=("it_glue", "datto_rmm"),
        )
        mappings.extend(endpoint_plan.mappings)

    acceptance = RealRecordCorrelationAcceptance(
        correlation_id=args.correlation_id.strip(),
        ticket_selector_sha256=sha256_text(args.ticket_number.strip()),
        stages=tuple(stages),
    )
    sanitized_mappings = [
        {
            "entity_type": item.entity_type.value,
            "provider": item.resource.provider,
            "resource_type": item.resource.resource_type,
            "resource_sha256": sha256_text(item.resource.external_id),
            "basis": item.basis.value,
            "verification": item.verification.value,
            "confidence": item.confidence,
            "provenance": item.provenance,
            "authoritative": item.authoritative,
        }
        for item in mappings
    ]
    payload = {
        "schema_version": "1.0",
        "observed_at": observed_at.isoformat(),
        "correlation_id": acceptance.correlation_id,
        "ticket_selector_sha256": acceptance.ticket_selector_sha256,
        "stages": [asdict(stage) for stage in acceptance.stages],
        "canonical_mappings": sanitized_mappings,
        "provider_reads": read_hashes,
        "connector_events": audit.connector_events,
        "orchestration_events": audit.orchestration_events,
        "hosted_model_used": acceptance.hosted_model_used,
        "hosted_model_input_tokens": acceptance.hosted_model_input_tokens,
        "hosted_model_output_tokens": acceptance.hosted_model_output_tokens,
        "hosted_model_cost_usd": acceptance.hosted_model_cost_usd,
        "raw_provider_payload_persisted": acceptance.raw_provider_payload_persisted,
        "raw_provider_payload_printed": acceptance.raw_provider_payload_printed,
        "durable_activation_mutated": False,
        "provider_data_changed": False,
        "read_only": True,
        "status": "pass",
    }
    payload["package_sha256"] = stable_payload_sha256(payload)
    _write_evidence(destination, payload)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    if args.live_read:
        print("PASS: bounded real-record correlation acceptance completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
