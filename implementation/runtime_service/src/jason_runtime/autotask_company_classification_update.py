from __future__ import annotations

"""Reusable, independently activation-gated Autotask Company classification update.

The caller supplies an exact expected state and an exact target state; the
provider-native patch is derived by Jason, never accepted as an arbitrary URL
or free-form patch. No runtime activation is granted by the source file.
"""

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.mutation_connector import AutotaskMutationConnector, autotask_mutation_execution_enabled
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import AuditSink, ConnectorAuthorizationError, ConnectorRequest, ConnectorResult, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, IdempotencyBehavior
from kernel.execution_providers import ExecutionProviderRegistryService, ProviderApproval, ProviderHealth, ProviderLifecycle
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker, ProviderPreparedExecution
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import _mutation_capability
from orchestrator.service import CapabilityInvoker
from .autotask_ticket_create import _ticket_create_provider
from .autotask_company_udf_admin import _positive_int

CAPABILITY = "service.company.classification.update"
PROVIDER = "autotask_company_classification_update"
OPERATION = "autotask.company.classification.update"
PROFILE_ENV = "JASON_AUTOTASK_COMPANY_CLASSIFICATION_UPDATE_PROFILE"
PROFILE = "owner-company-classification-v1"
TYPE_PROSPECT = 3
TYPE_CUSTOMER = 1
UDF_NAME = "CW_CompanyType"
UDF_PROSPECT = "Prospect"
UDF_CUSTOMER = "Client"  # Existing AOT normalization, rather than inventing a new label.


class CompanyClassificationError(PermissionError):
    pass


def enabled() -> bool:
    value = os.getenv(PROFILE_ENV, "").strip()
    if not value:
        return False
    if value != PROFILE:
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_PROFILE_INVALID")
    if not autotask_mutation_execution_enabled():
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_MUTATION_DISABLED")
    return True


def _state(company: Mapping[str, Any], company_id: int) -> tuple[str, int, str, tuple[tuple[str, str | None], ...]]:
    if _positive_int(company.get("id"), field="company id") != company_id:
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_ID_MISMATCH")
    name = company.get("companyName")
    if not isinstance(name, str) or not name.strip():
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_NAME_MISSING")
    kind = company.get("companyType")
    if type(kind) is not int:
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_TYPE_INVALID")
    fields = company.get("userDefinedFields")
    if not isinstance(fields, list):
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDFS_INVALID")
    encountered: set[str] = set()
    udf = None
    others: list[tuple[str, str | None]] = []
    for f in fields:
        if not isinstance(f, Mapping) or not isinstance(f.get("name"), str):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDFS_INVALID")
        key, value = f["name"], f.get("value")
        if key in encountered or (value is not None and not isinstance(value, str)):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDFS_AMBIGUOUS")
        encountered.add(key)
        if key == UDF_NAME:
            udf = value
        else:
            others.append((key, value))
    if UDF_NAME not in encountered:
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDF_MISSING")
    if udf not in (UDF_PROSPECT, UDF_CUSTOMER):
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDF_UNEXPECTED")
    return name, kind, udf, tuple(sorted(others))


@dataclass(frozen=True, slots=True)
class PreparedCompany:
    request: ConnectorRequest
    prepared: PreparedRequest
    company_id: int
    before: tuple[str, int, str, tuple[tuple[str, str | None], ...]]
    after_type: int
    after_udf: str


class CompanyClassificationConnector(AutotaskMutationConnector):
    capabilities = frozenset({OPERATION})
    operation_preflight = {OPERATION: ("Companies", "userAccessForUpdate")}
    logical_secret = "autotask.write"

    def _get(self, prepared: PreparedRequest, company_id: int) -> Mapping[str, Any]:
        response = self._transport.request(
            method="GET", url=f"{self._api_root(prepared)}/V1.0/Companies/{company_id}",
            headers=prepared.headers, params=None, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        item = response.get("item", response) if isinstance(response, Mapping) else None
        if not isinstance(item, Mapping):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_READ_INVALID")
        return item

    @staticmethod
    def _payload(args: Any) -> tuple[int, int, str, int, str]:
        if not isinstance(args, Mapping) or set(args) != {"company_id", "expected_company_type", "expected_udf", "target_company_type", "target_udf"}:
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_ARGUMENTS_INVALID")
        company_id = _positive_int(args["company_id"], field="company_id")
        expected_type = args["expected_company_type"]
        target_type = args["target_company_type"]
        expected_udf = args["expected_udf"]
        target_udf = args["target_udf"]
        if type(expected_type) is not int or type(target_type) is not int:
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_TYPE_INVALID")
        if not isinstance(expected_udf, str) or not isinstance(target_udf, str):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_UDF_INVALID")
        # Explicitly support a reversible Prospect <-> Customer/Client transition.
        allowed = ((TYPE_PROSPECT, UDF_PROSPECT, TYPE_CUSTOMER, UDF_CUSTOMER),
                   (TYPE_CUSTOMER, UDF_CUSTOMER, TYPE_PROSPECT, UDF_PROSPECT))
        if (expected_type, expected_udf, target_type, target_udf) not in allowed:
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_TRANSITION_NOT_ALLOWED")
        return company_id, expected_type, expected_udf, target_type, target_udf

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        if request.context.capability != OPERATION or request.context.mode != "execute":
            raise ConnectorAuthorizationError("Company classification action not authorized")
        if not enabled():
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_NOT_ACTIVE")
        company_id, old_type, old_udf, new_type, new_udf = self._payload(request.arguments.get("payload"))
        patch = {"id": company_id, "companyType": new_type,
                 "userDefinedFields": [{"name": UDF_NAME, "value": new_udf}]}
        normalized = ConnectorRequest(context=request.context,
                                      arguments={**dict(request.arguments), "payload": patch})
        creds = self._secrets.resolve(self.logical_secret, normalized.context)
        prepared = AutotaskMutationConnector.prepare_request(self, normalized, creds)
        before = _state(self._get(prepared, company_id), company_id)
        if before[1:3] != (old_type, old_udf):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_EXPECTED_STATE_MISMATCH")
        return ProviderPreparedExecution(
            provider_capability=OPERATION, action_method=prepared.method,
            resource_type="service_company", resource_identifier=str(company_id),
            normalized_path=prepared.audit_operation or urlsplit(prepared.url).path,
            payload=dict(prepared.json or {}), parameters=dict(prepared.params or {}),
            symbolic_resolutions={},
            opaque=PreparedCompany(normalized, prepared, company_id, before, new_type, new_udf),
        )

    def execute_governed_execution(self, plan: ProviderPreparedExecution) -> ConnectorResult:
        opaque = plan.opaque
        if not isinstance(opaque, PreparedCompany):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_PLAN_INVALID")
        request, prepared = opaque.request, opaque.prepared
        if (plan.provider_capability != OPERATION or plan.action_method != prepared.method
                or plan.resource_identifier != str(opaque.company_id)
                or plan.resource_type != "service_company"
                or normalize_provider_relative_path(plan.normalized_path) != normalize_provider_relative_path(prepared.audit_operation or urlsplit(prepared.url).path)
                or dict(plan.payload) != dict(prepared.json or {})
                or dict(plan.parameters) != dict(prepared.params or {})):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_PLAN_MISMATCH")
        if not enabled():
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_NOT_ACTIVE")
        if _state(self._get(prepared, opaque.company_id), opaque.company_id) != opaque.before:
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_CONCURRENT_CHANGE")
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            response = self._transport.request(
                method=prepared.method, url=prepared.url,
                headers=prepared.headers, params=prepared.params, json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as exc:
            self._audit_mutation_event("connector.mutation.failed", request, error_type=type(exc).__name__)
            raise
        if not isinstance(response, Mapping):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_RESPONSE_INVALID")
        response_id = response.get("itemId") or response.get("id")
        if response_id is not None and _positive_int(response_id, field="response id") != opaque.company_id:
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_RESPONSE_ID_MISMATCH")
        after = _state(self._get(prepared, opaque.company_id), opaque.company_id)
        if after != (opaque.before[0], opaque.after_type, opaque.after_udf, opaque.before[3]):
            raise CompanyClassificationError("COMPANY_CLASSIFICATION_READBACK_MISMATCH")
        self._audit_mutation_event("connector.mutation.completed", request)
        return ConnectorResult(
            capability=OPERATION, provider=self.provider_name,
            data={"itemId": opaque.company_id, "jasonVerification": {
                "readbackVerified": True, "companyType": opaque.after_type,
                "CW_CompanyType": opaque.after_udf, "unrelatedUdfsPreserved": True}},
            evidence_ids=(f"autotask:company:{opaque.company_id}",),
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(self.prepare_governed_execution(request))


def register_foundation(*, capabilities: CapabilityRegistryService,
                        providers: ExecutionProviderRegistryService, now: datetime) -> bool:
    definition = _mutation_capability(
        now=now, capability_name=CAPABILITY,
        display_name="Update Autotask Company classification",
        business_purpose="Reversibly correct verified Autotask company Prospect/Customer classification",
        resource_types="service_company", operation="update",
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
    )
    capabilities.register(replace(definition, client_isolation_required=False,
        metadata={**dict(definition.metadata), "mcp_action_enabled": "true",
                  "mcp_tool_name": "execute_governed_capability", "activation_state": "source_only"}))
    provider = replace(_ticket_create_provider(now=now), provider_id=PROVIDER,
        display_name="Autotask Company Classification Update", capabilities=frozenset({CAPABILITY}),
        metadata={"activation_state": "source_only", "mutation_scope": "company_classification"})
    providers.register(provider)
    if not os.getenv(PROFILE_ENV, "").strip():
        return False
    if not enabled():
        raise CompanyClassificationError("COMPANY_CLASSIFICATION_PROFILE_INVALID")
    capabilities.set_lifecycle(capability_name=CAPABILITY, version="1.0",
                               lifecycle_status=CapabilityLifecycle.ACTIVE)
    providers.set_approval(provider_id=PROVIDER, approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=PROVIDER, health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=PROVIDER, lifecycle_status=ProviderLifecycle.AVAILABLE)
    return True


def build_invoker(*, openbao_url: str, role_id_path: Path, secret_id_path: Path,
                  transport: HttpTransport, audit: AuditSink,
                  bindings: TrustedPrincipalBindingResolver) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(base_url=openbao_url, role_id_path=role_id_path,
                                    secret_id_path=secret_id_path)
    connector = CompanyClassificationConnector(secrets=secrets, transport=transport,
                                               audit=audit, bindings=bindings)
    return GovernedConnectorCapabilityInvoker(
        connectors={PROVIDER: connector}, provider_capability_map={(PROVIDER, CAPABILITY): OPERATION})


def register_invoker(*, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker) -> None:
    invokers.register(CAPABILITY, invoker)
