from __future__ import annotations

"""Dormant, governed, exact Company outbound-consent UDF update.

One reusable provider-native Company UDF writer; it is not a sender.  No
Company record is writable until separate runtime activation, exact action
approval, native requester permission and schema/readback checks all pass.
"""

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.mutation_connector import (
    AutotaskMutationConnector, autotask_mutation_execution_enabled,
)
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorRequest, ConnectorResult,
    HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, ProviderApproval, ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.connector_invoker import (
    GovernedConnectorCapabilityInvoker, ProviderPreparedExecution,
)
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import _mutation_capability
from orchestrator.service import CapabilityInvoker

from .autotask_ticket_create import _ticket_create_provider
from .client_outbound_opt_in import CLIENT_OUTBOUND_OPT_IN_FIELD
from .autotask_company_udf_admin import _positive_int

SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE = "service.company.outbound.optin.update"
AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER = "autotask_company_outbound_optin"
AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV = (
    "JASON_AUTOTASK_COMPANY_OUTBOUND_OPTIN_PROFILE"
)
AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE = "owner-company-outbound-optin-v1"
_AUTOTASK_OPERATION = "autotask.company.outbound.optin.update"


class AutotaskCompanyOutboundOptInError(PermissionError):
    """Fail-closed Company consent update, authority or readback issue."""


@dataclass(frozen=True, slots=True)
class _Prepared:
    request: ConnectorRequest
    prepared: PreparedRequest
    company_id: int
    target_value: str
    previous_value: str | None
    prior_other_fields: tuple[tuple[str, str | None], ...]
    company_name: str


def company_outbound_opt_in_update_enabled() -> bool:
    profile = os.getenv(AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV, "").strip()
    if not profile:
        return False
    if profile != AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE:
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_PROFILE_INVALID"
        )
    if not autotask_mutation_execution_enabled():
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_MUTATION_DISABLED"
        )
    return True


def _parse_existing_company(company: Mapping[str, Any], company_id: int):
    if _positive_int(company.get("id"), field="company record id") != company_id:
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_COMPANY_MISMATCH"
        )
    name = company.get("companyName")
    if not isinstance(name, str) or not name.strip():
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_COMPANY_NAME_MISSING"
        )
    fields = company.get("userDefinedFields", [])
    if not isinstance(fields, list):
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_FIELDS_INVALID"
        )
    values: list[str | None] = []
    other: list[tuple[str, str | None]] = []
    seen_names: set[str] = set()
    for item in fields:
        if not isinstance(item, Mapping):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_FIELDS_INVALID"
            )
        key = item.get("name")
        raw = item.get("value")
        if not isinstance(key, str) or key in seen_names or (
            raw is not None and not isinstance(raw, str)
        ):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_FIELDS_AMBIGUOUS"
            )
        seen_names.add(key)
        if key == CLIENT_OUTBOUND_OPT_IN_FIELD:
            values.append(raw)
        else:
            other.append((key, raw))
    if len(values) > 1:
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_FIELDS_AMBIGUOUS"
        )
    old = values[0] if values else None
    if old not in (None, "", "True", "False"):
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_EXISTING_VALUE_INVALID"
        )
    return old, tuple(sorted(other)), name


class AutotaskCompanyOutboundOptInConnector(AutotaskMutationConnector):
    """Change only the approved company-level outbound-consent field."""

    capabilities = frozenset({_AUTOTASK_OPERATION})
    operation_preflight = {
        _AUTOTASK_OPERATION: ("Companies", "userAccessForUpdate"),
    }
    logical_secret = "autotask.write"

    @staticmethod
    def validated_payload(payload: Any) -> tuple[int, str, Mapping[str, Any]]:
        if not isinstance(payload, Mapping) or set(payload) != {"company_id", "enabled"}:
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_SCOPE_INVALID"
            )
        company_id = _positive_int(payload["company_id"], field="company_id")
        if type(payload["enabled"]) is not bool:
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_ENABLED_MUST_BE_BOOLEAN"
            )
        value = "True" if payload["enabled"] else "False"
        patch = {
            "id": company_id,
            "userDefinedFields": [
                {"name": CLIENT_OUTBOUND_OPT_IN_FIELD, "value": value}
            ],
        }
        return company_id, value, patch

    def _get(self, prepared: PreparedRequest, entity: str, record_id: int):
        response = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/{entity}/{record_id}",
            headers=prepared.headers,
            params=None, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(response, Mapping):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_GET_INVALID"
            )
        item = response.get("item", response)
        if not isinstance(item, Mapping):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_GET_INVALID"
            )
        return item

    def _require_schema(self, prepared: PreparedRequest) -> None:
        search = json.dumps(
            {"MaxRecords": 2, "filter": [{
                "op": "eq", "field": "name", "value": CLIENT_OUTBOUND_OPT_IN_FIELD
            }]},
            separators=(",", ":"), sort_keys=True,
        )
        response = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/UserDefinedFieldDefinitions/query",
            headers=prepared.headers,
            params={"search": search}, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(response, Mapping) or not isinstance(
            response.get("items"), list
        ):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_SCHEMA_QUERY_INVALID"
            )
        definitions = response["items"]
        if len(definitions) != 1 or not isinstance(definitions[0], Mapping):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_SCHEMA_NOT_UNIQUE"
            )
        d = definitions[0]
        if (
            d.get("name") != CLIENT_OUTBOUND_OPT_IN_FIELD
            or d.get("isActive") is not True
            or d.get("isVisibleToClientPortal") is not False
            or int(d.get("udfType") or 0) != 1
            or int(d.get("dataType") or 0) != 3
        ):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_SCHEMA_INVALID"
            )
        definition_id = _positive_int(d.get("id"), field="UDF definition id")
        choices_search = json.dumps(
            {"MaxRecords": 100, "filter": [{
                "op": "eq", "field": "udfFieldId", "value": definition_id
            }]},
            separators=(",", ":"), sort_keys=True,
        )
        choices = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/UserDefinedFieldListItems/query",
            headers=prepared.headers,
            params={"search": choices_search}, json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if (
            not isinstance(choices, Mapping)
            or not isinstance(choices.get("items"), list)
            or len(choices["items"]) != 2
            or (isinstance(choices.get("pageDetails"), Mapping)
                and choices["pageDetails"].get("nextPageUrl"))
        ):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_CHOICES_INVALID"
            )
        observed = set()
        for item in choices["items"]:
            if not isinstance(item, Mapping) or item.get("isActive") is not True:
                raise AutotaskCompanyOutboundOptInError(
                    "AUTOTASK_COMPANY_OUTBOUND_OPTIN_CHOICES_INVALID"
                )
            display, exported = item.get("valueForDisplay"), item.get("valueForExport")
            if display != exported or display not in {"True", "False"}:
                raise AutotaskCompanyOutboundOptInError(
                    "AUTOTASK_COMPANY_OUTBOUND_OPTIN_CHOICES_INVALID"
                )
            observed.add(display)
        if observed != {"True", "False"}:
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_CHOICES_INVALID"
            )

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        if request.context.capability != _AUTOTASK_OPERATION:
            raise ConnectorAuthorizationError("Company outbound opt-in operation not registered")
        if request.context.mode != "execute" or not company_outbound_opt_in_update_enabled():
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_NOT_ACTIVE"
            )
        company_id, target, patch = self.validated_payload(
            request.arguments.get("payload")
        )
        normalized = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": patch},
        )
        creds = self._secrets.resolve(self.logical_secret, normalized.context)
        prepared = AutotaskMutationConnector.prepare_request(self, normalized, creds)
        # Provider-native impersonated Company UPDATE permission is already
        # required by prepare_request before any Company record is modified.
        self._require_schema(prepared)
        company = self._get(prepared, "Companies", company_id)
        old, other, name = _parse_existing_company(company, company_id)
        if old == target:
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_ALREADY_SET"
            )
        return ProviderPreparedExecution(
            provider_capability=normalized.context.capability,
            action_method=prepared.method,
            resource_type="service_company",
            resource_identifier=str(company_id),
            normalized_path=prepared.audit_operation or urlsplit(prepared.url).path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions={},
            opaque=_Prepared(
                request=normalized, prepared=prepared, company_id=company_id,
                target_value=target, previous_value=old,
                prior_other_fields=other, company_name=name,
            ),
        )

    def execute_governed_execution(self, plan: ProviderPreparedExecution) -> ConnectorResult:
        opaque = plan.opaque
        if not isinstance(opaque, _Prepared):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_INVALID_PLAN"
            )
        request, prepared = opaque.request, opaque.prepared
        if (
            plan.provider_capability != request.context.capability
            or plan.action_method != prepared.method
            or plan.resource_type != "service_company"
            or plan.resource_identifier != str(opaque.company_id)
            or normalize_provider_relative_path(plan.normalized_path)
            != normalize_provider_relative_path(prepared.audit_operation or urlsplit(prepared.url).path)
            or dict(plan.payload) != dict(prepared.json or {})
            or dict(plan.parameters) != dict(prepared.params or {})
        ):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_PLAN_MISMATCH"
            )
        if not company_outbound_opt_in_update_enabled():
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_NOT_ACTIVE"
            )
        self._require_schema(prepared)
        before = self._get(prepared, "Companies", opaque.company_id)
        old, others, name = _parse_existing_company(before, opaque.company_id)
        if (old != opaque.previous_value or others != opaque.prior_other_fields
                or name != opaque.company_name):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_CONCURRENT_CHANGE"
            )
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            response = self._transport.request(
                method=prepared.method,
                url=prepared.url,
                headers=prepared.headers,
                params=prepared.params, json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as exc:
            self._audit_mutation_event(
                "connector.mutation.failed", request, error_type=type(exc).__name__
            )
            raise
        if not isinstance(response, Mapping):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_PROVIDER_RESPONSE_INVALID"
            )
        response_id = response.get("itemId") or response.get("id")
        if response_id is not None and _positive_int(
            response_id, field="provider itemId"
        ) != opaque.company_id:
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_RESPONSE_ID_MISMATCH"
            )
        after = self._get(prepared, "Companies", opaque.company_id)
        value, other_after, name_after = _parse_existing_company(
            after, opaque.company_id
        )
        if (value != opaque.target_value or other_after != opaque.prior_other_fields
                or name_after != opaque.company_name):
            raise AutotaskCompanyOutboundOptInError(
                "AUTOTASK_COMPANY_OUTBOUND_OPTIN_READBACK_MISMATCH"
            )
        self._audit_mutation_event("connector.mutation.completed", request)
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={
                "itemId": opaque.company_id,
                "jasonVerification": {
                    "readbackVerified": True,
                    "companyID": opaque.company_id,
                    "field": CLIENT_OUTBOUND_OPT_IN_FIELD,
                    "value": value,
                    "unrelatedUdfsPreserved": True,
                },
            },
            evidence_ids=(f"autotask:company:{opaque.company_id}",),
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(
            self.prepare_governed_execution(request)
        )


def _definition(now: datetime):
    base = _mutation_capability(
        now=now,
        capability_name=SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE,
        display_name="Update Autotask Company outbound communication consent",
        business_purpose="Set the exact Company UDF outbound communication opt-in.",
        resource_types="service_company",
        operation="update",
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
    )
    return replace(
        base, client_isolation_required=False,
        metadata={
            **dict(base.metadata),
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "activation_state": "company_outbound_optin_source_only",
            "provider_credential": "autotask.write",
            "controlled_field": CLIENT_OUTBOUND_OPT_IN_FIELD,
        },
    )


def _provider(now: datetime):
    base = _ticket_create_provider(now=now)
    return replace(
        base,
        provider_id=AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
        display_name="Autotask Company Outbound Opt-In Update",
        capabilities=frozenset({SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE}),
        metadata={
            **dict(base.metadata),
            "activation_state": "company_outbound_optin_source_only",
            "mutation_scope": "one_verified_company_outbound_optin_field",
        },
    )


def register_autotask_company_outbound_opt_in_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService, now: datetime,
) -> bool:
    capabilities.register(_definition(now))
    providers.register(_provider(now))
    if not os.getenv(AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV, "").strip():
        return False
    if not company_outbound_opt_in_update_enabled():
        raise AutotaskCompanyOutboundOptInError(
            "AUTOTASK_COMPANY_OUTBOUND_OPTIN_PROFILE_INVALID"
        )
    capabilities.set_lifecycle(
        capability_name=SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE,
        version="1.0", lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return True


def build_autotask_company_outbound_opt_in_invoker(
    *, openbao_url: str, role_id_path: Path, secret_id_path: Path,
    transport: HttpTransport, audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url, role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = AutotaskCompanyOutboundOptInConnector(
        secrets=secrets, transport=transport, audit=audit, bindings=bindings,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER: connector},
        provider_capability_map={
            (
                AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
                SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE,
            ): _AUTOTASK_OPERATION,
        },
    )


def register_autotask_company_outbound_opt_in_invoker(
    *, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker,
) -> None:
    invokers.register(SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE, invoker)
