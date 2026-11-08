from __future__ import annotations

"""Dormant, provider-impersonated Company list-UDF administration.

Never creates records without the Central Orchestrator's approved, exact
execution plan. Uses only the two static supported Autotask REST endpoints.
"""

import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
    autotask_mutation_execution_enabled,
)
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorRequest,
    ConnectorResult, HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, IdempotencyBehavior
from kernel.execution_providers import (
    ExecutionProviderRegistryService, ProviderApproval, ProviderHealth, ProviderLifecycle,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker, ProviderPreparedExecution
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import _mutation_capability
from orchestrator.service import CapabilityInvoker

from .autotask_ticket_create import _ticket_create_provider


SERVICE_COMPANY_UDF_DEFINITION_CREATE = "service.company.udf.definition.create"
SERVICE_COMPANY_UDF_CHOICE_CREATE = "service.company.udf.choice.create"
AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER = "autotask_company_udf_admin"
AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV = "JASON_AUTOTASK_COMPANY_UDF_ADMIN_PROFILE"
AUTOTASK_COMPANY_UDF_ADMIN_PROFILE = "owner-company-udf-admin-v1"

_DEFINITION_CREATE = "autotask.udf.definition.create"
_CHOICE_CREATE = "autotask.udf.list.item.create"
_OPERATIONS = frozenset({_DEFINITION_CREATE, _CHOICE_CREATE})
_PREFLIGHT = {
    _DEFINITION_CREATE: ("UserDefinedFieldDefinitions", "userAccessForCreate"),
    _CHOICE_CREATE: ("UserDefinedFieldListItems", "userAccessForCreate"),
}
_CAPABILITIES = frozenset({SERVICE_COMPANY_UDF_DEFINITION_CREATE, SERVICE_COMPANY_UDF_CHOICE_CREATE})
_PROVIDER_MAP = {
    (AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER, SERVICE_COMPANY_UDF_DEFINITION_CREATE): _DEFINITION_CREATE,
    (AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER, SERVICE_COMPANY_UDF_CHOICE_CREATE): _CHOICE_CREATE,
}
_RESOURCE_ENTITIES = {
    _DEFINITION_CREATE: "UserDefinedFieldDefinitions",
    _CHOICE_CREATE: "UserDefinedFieldListItems",
}


class AutotaskCompanyUdfAdminError(PermissionError):
    """A Company UDF administration gate or provider verification failed."""


@dataclass(frozen=True, slots=True)
class _Prepared:
    request: ConnectorRequest
    expected: Mapping[str, Any]
    prepared: PreparedRequest
    entity: str


def _positive_int(raw: Any, *, field: str) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"{field} must be a positive integer")
    try:
        value = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _text(raw: Any, *, field: str, limit: int) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be text")
    value = raw.strip()
    if not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"{field} must be bounded printable text")
    return value


def company_udf_admin_enabled() -> bool:
    profile = os.getenv(AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, "").strip()
    if not profile:
        return False
    if profile != AUTOTASK_COMPANY_UDF_ADMIN_PROFILE:
        raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_PROFILE_INVALID")
    if not autotask_mutation_execution_enabled():
        raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_MUTATION_DISABLED")
    return True


class AutotaskCompanyUdfAdminConnector(AutotaskMutationConnector):
    """Requester-impersonated, bounded Company list-UDF definition and choice creates."""

    capabilities = _OPERATIONS
    operation_preflight = _PREFLIGHT
    logical_secret = "autotask.write"

    @staticmethod
    def validated_payload(operation: str, payload: Any) -> dict[str, Any]:
        if operation not in _OPERATIONS:
            raise ConnectorAuthorizationError("Company UDF admin operation not registered")
        if not isinstance(payload, Mapping):
            raise ValueError("Company UDF admin requires a structured payload")
        raw = dict(payload)
        if operation == _DEFINITION_CREATE:
            allow = {"name", "description"}
            if set(raw) - allow:
                raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_FIELD_NOT_ALLOWED")
            name = _text(raw.get("name"), field="name", limit=80)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,79}", name):
                raise ValueError("Company UDF name must be a safe identifier")
            description = raw.get("description", "")
            if not isinstance(description, str) or len(description) > 500:
                raise ValueError("Company UDF description exceeds bounded text limit")
            # Native metadata 2026-11-08: udfType=1 Account; dataType=3 List.
            # No native default selected until choices are created. Missing
            # values are treated as False by the separate send decision gate.
            return {
                "name": name, "description": description.strip(),
                "udfType": 1, "dataType": 3,
                "defaultValue": "", "isRequired": False,
                "isVisibleToClientPortal": False,
                "isActive": True, "isPrivate": False, "isProtected": False,
                "isEncrypted": False,
            }
        if set(raw) != {"udfFieldId", "valueForDisplay", "valueForExport"}:
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_CHOICE_FIELDS_INVALID")
        display = _text(raw.get("valueForDisplay"), field="valueForDisplay", limit=64)
        exported = _text(raw.get("valueForExport"), field="valueForExport", limit=64)
        return {
            "udfFieldId": _positive_int(raw.get("udfFieldId"), field="udfFieldId"),
            "valueForDisplay": display,
            "valueForExport": exported,
            "isActive": True,
        }

    def _query(self, prepared: PreparedRequest, entity: str, field: str, value: Any) -> list[Mapping[str, Any]]:
        url = f"{self._api_root(prepared)}/V1.0/{entity}/query"
        # Exact-name existence checks need at most two records.  A choice
        # duplicate check must inspect the entire bounded set for that UDF,
        # otherwise a 2-item page could silently miss a duplicate choice.
        limit = 500 if entity == "UserDefinedFieldListItems" else 2
        search = json.dumps(
            {"MaxRecords": limit, "filter": [{"op": "eq", "field": field, "value": value}]},
            separators=(",", ":"), sort_keys=True,
        )
        result = self._transport.request(
            method="GET", url=url, headers=prepared.headers,
            params={"search": search}, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(result, Mapping) or not isinstance(result.get("items"), list):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_PREFLIGHT_QUERY_INVALID")
        details = result.get("pageDetails")
        if (len(result["items"]) >= limit
                or isinstance(details, Mapping) and details.get("nextPageUrl")):
            raise AutotaskCompanyUdfAdminError(
                "AUTOTASK_COMPANY_UDF_PREFLIGHT_QUERY_INCOMPLETE"
            )
        return result["items"]

    def _get(self, prepared: PreparedRequest, entity: str, durable_id: int) -> Mapping[str, Any]:
        result = self._transport.request(
            method="GET", url=f"{self._api_root(prepared)}/V1.0/{entity}/{durable_id}",
            headers=prepared.headers, params=None, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(result, Mapping):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_READBACK_INVALID")
        item = result.get("item", result)
        if not isinstance(item, Mapping):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_READBACK_INVALID")
        return item

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        if request.context.capability not in _OPERATIONS:
            raise ConnectorAuthorizationError("Company UDF operation not registered")
        if request.context.mode != "execute" or not company_udf_admin_enabled():
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_ADMIN_NOT_ACTIVE")
        expected = self.validated_payload(
            request.context.capability, request.arguments.get("payload")
        )
        normalized = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": expected},
        )
        credentials = self._secrets.resolve(self.logical_secret, normalized.context)
        prepared = AutotaskMutationConnector.prepare_request(self, normalized, credentials)
        # Preflight durable duplicate behavior and owner-scoped Company UDF.
        if normalized.context.capability == _DEFINITION_CREATE:
            matches = self._query(prepared, "UserDefinedFieldDefinitions", "name", expected["name"])
            if matches:
                raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_ALREADY_EXISTS")
        else:
            definition = self._get(
                prepared, "UserDefinedFieldDefinitions", expected["udfFieldId"]
            )
            if (
                definition.get("isActive") is not True
                or definition.get("udfType") != 1
                or definition.get("dataType") != 3
            ):
                raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_DEFINITION_NOT_ACTIVE_LIST")
            existing = self._query(
                prepared, "UserDefinedFieldListItems",
                "udfFieldId", expected["udfFieldId"],
            )
            if any(
                item.get("valueForDisplay") == expected["valueForDisplay"]
                or item.get("valueForExport") == expected["valueForExport"]
                for item in existing
            ):
                raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_CHOICE_ALREADY_EXISTS")
        return ProviderPreparedExecution(
            provider_capability=normalized.context.capability,
            action_method=prepared.method,
            resource_type="autotask_company_udf_schema",
            resource_identifier=None,
            normalized_path=prepared.audit_operation or urlsplit(prepared.url).path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions={},
            opaque=_Prepared(normalized, expected, prepared, _RESOURCE_ENTITIES[normalized.context.capability]),
        )

    def execute_governed_execution(self, plan: ProviderPreparedExecution) -> ConnectorResult:
        opaque = plan.opaque
        if not isinstance(opaque, _Prepared):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_INVALID_PLAN")
        request, expected, prepared, entity = opaque.request, opaque.expected, opaque.prepared, opaque.entity
        if (
            plan.provider_capability != request.context.capability
            or plan.action_method != prepared.method
            or plan.resource_identifier is not None
            or normalize_provider_relative_path(plan.normalized_path)
            != normalize_provider_relative_path(prepared.audit_operation or urlsplit(prepared.url).path)
            or dict(plan.payload) != dict(prepared.json or {})
            or dict(plan.parameters) != dict(prepared.params or {})
        ):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_PLAN_MISMATCH")
        if not company_udf_admin_enabled():
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_ADMIN_NOT_ACTIVE")
        # Recheck the immutable target immediately before POST.  The
        # original prepare-time query can become stale while a human reviews
        # the exact execution plan; never create a second definition/choice.
        if request.context.capability == _DEFINITION_CREATE:
            if self._query(prepared, entity, "name", expected["name"]):
                raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_ALREADY_EXISTS")
        else:
            definition = self._get(
                prepared, "UserDefinedFieldDefinitions", expected["udfFieldId"]
            )
            if (definition.get("isActive") is not True
                    or definition.get("udfType") != 1
                    or definition.get("dataType") != 3):
                raise AutotaskCompanyUdfAdminError(
                    "AUTOTASK_COMPANY_UDF_DEFINITION_NOT_ACTIVE_LIST"
                )
            existing = self._query(
                prepared, entity, "udfFieldId", expected["udfFieldId"]
            )
            if any(
                item.get("valueForDisplay") == expected["valueForDisplay"]
                or item.get("valueForExport") == expected["valueForExport"]
                for item in existing
            ):
                raise AutotaskCompanyUdfAdminError(
                    "AUTOTASK_COMPANY_UDF_CHOICE_ALREADY_EXISTS"
                )
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            response = self._transport.request(
                method=prepared.method, url=prepared.url, headers=prepared.headers,
                params=prepared.params, json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as exc:
            self._audit_mutation_event(
                "connector.mutation.failed", request, error_type=type(exc).__name__
            )
            raise
        if not isinstance(response, Mapping):
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_CREATE_ID_MISSING")
        raw_id = response.get("itemId") or response.get("id")
        if raw_id is None and isinstance(response.get("item"), Mapping):
            raw_id = response["item"].get("id")
        durable_id = _positive_int(raw_id, field="created UDF record")
        actual = self._get(prepared, entity, durable_id)
        if _positive_int(actual.get("id"), field="readback id") != durable_id:
            raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_ID_MISMATCH")
        for key, value in expected.items():
            if actual.get(key) != value:
                raise AutotaskCompanyUdfAdminError(
                    "AUTOTASK_COMPANY_UDF_READBACK_FIELD_MISMATCH"
                )
        self._audit_mutation_event("connector.mutation.completed", request)
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={
                "itemId": durable_id,
                "jasonVerification": {
                    "readbackVerified": True,
                    "resourceId": durable_id,
                    "entity": entity,
                    "verifiedFields": sorted(expected),
                },
            },
            evidence_ids=(f"autotask:{entity}:{durable_id}",),
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(self.prepare_governed_execution(request))


def _definitions(now: datetime):
    specifications = (
        (SERVICE_COMPANY_UDF_DEFINITION_CREATE, "Create Autotask Company UDF",
         "Create one approved Autotask Company list-type custom field."),
        (SERVICE_COMPANY_UDF_CHOICE_CREATE, "Create Autotask Company UDF Choice",
         "Create one approved choice for an existing Company list-type custom field."),
    )
    result = []
    for name, title, purpose in specifications:
        base = _mutation_capability(
            now=now, capability_name=name, display_name=title,
            business_purpose=purpose, resource_types="service_company_udf",
            operation="create", idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        )
        result.append(replace(
            base, client_isolation_required=False,
            metadata={
                **dict(base.metadata),
                "mcp_action_enabled": "true",
                "mcp_tool_name": "execute_governed_capability",
                "activation_state": "company_udf_source_only_not_activated",
                "provider_credential": "autotask.write",
                "pilot_scope": "owner_company_udf_admin",
            },
        ))
    return tuple(result)


def _provider(now: datetime):
    base = _ticket_create_provider(now=now)
    return replace(
        base,
        provider_id=AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER,
        display_name="Autotask Governed Company UDF Administration",
        capabilities=_CAPABILITIES,
        metadata={
            **dict(base.metadata),
            "mutation_scope": "company_udf_definition_and_choice_create_only",
            "activation_state": "company_udf_source_only_not_activated",
        },
    )


def register_autotask_company_udf_admin_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService, now: datetime,
) -> bool:
    for definition in _definitions(now):
        capabilities.register(definition)
    providers.register(_provider(now))
    if not os.getenv(AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, "").strip():
        return False
    if not company_udf_admin_enabled():
        raise AutotaskCompanyUdfAdminError("AUTOTASK_COMPANY_UDF_PROFILE_INVALID")
    for name in sorted(_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return True


def build_autotask_company_udf_admin_invoker(
    *, openbao_url: str, role_id_path: Path, secret_id_path: Path,
    transport: HttpTransport, audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url, role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = AutotaskCompanyUdfAdminConnector(
        secrets=secrets, transport=transport, audit=audit, bindings=bindings,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER: connector},
        provider_capability_map=_PROVIDER_MAP,
    )


def register_autotask_company_udf_admin_invoker(
    *, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker,
) -> None:
    for capability in sorted(_CAPABILITIES):
        invokers.register(capability, invoker)
