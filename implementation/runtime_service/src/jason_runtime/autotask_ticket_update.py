from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Mapping

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import (
    TrustedPrincipalBindingResolver,
)
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
    autotask_mutation_execution_enabled,
)
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import (
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.connector_invoker import (
    GovernedConnectorCapabilityInvoker,
    ProviderPreparedExecution,
)
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_UPDATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker


AUTOTASK_TICKET_UPDATE_PROVIDER = "autotask_ticket_update"

AUTOTASK_TICKET_UPDATE_PROFILE_ENV = (
    "JASON_AUTOTASK_TICKET_UPDATE_MCP_PROFILE"
)

AUTOTASK_TICKET_UPDATE_PROFILE = "owner-ticket-update-v1"

AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_ENV = (
    "JASON_AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID"
)
AUTOTASK_TICKET_UPDATE_AUTONOMY_PRINCIPAL = "jason-autonomy-worker"


def configured_autotask_ticket_update_autonomy_resource_id() -> int | None:
    raw = os.getenv(AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError("AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_INVALID") from error
    if value < 1:
        raise RuntimeError("AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_INVALID")
    return value

SAFE_TICKET_UPDATE_FIELDS = frozenset(
    {
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "dueDateTime",
        "configurationItemID",
        "billingCodeID",
        "issueType",
        "subIssueType",
        "ticketType",
    }
)

_INTEGER_FIELDS = frozenset(
    {
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "configurationItemID",
        "billingCodeID",
        "issueType",
        "subIssueType",
        "ticketType",
    }
)

_TICKET_PICKLIST_LABEL_FIELDS = (
    "status",
    "queueID",
    "ticketType",
    "issueType",
    "subIssueType",
)

_PROVIDER_CAPABILITY_MAP = {
    (
        AUTOTASK_TICKET_UPDATE_PROVIDER,
        SERVICE_TICKET_UPDATE,
    ): "autotask.ticket.update",
}


class AutotaskTicketUpdateActivationError(RuntimeError):
    pass


class AutotaskTicketUpdateVerificationError(ConnectorError):
    error_code = "AUTOTASK_TICKET_UPDATE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class AutotaskTicketUpdateActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PreparedAutotaskTicketUpdate:
    request: ConnectorRequest
    expected: Mapping[str, Any]
    prepared: PreparedRequest


def autotask_ticket_update_mcp_surface_enabled() -> bool:
    profile = os.getenv(
        AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
        "",
    ).strip().casefold()

    mutation_enabled = os.getenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "",
    ).strip().casefold()

    return (
        profile == AUTOTASK_TICKET_UPDATE_PROFILE
        and mutation_enabled == "true"
    )


def _ticket_update_definition(*, now: datetime):
    matches = [
        definition
        for definition in autotask_mutation_capability_definitions(
            now=now
        )
        if definition.capability_name == SERVICE_TICKET_UPDATE
    ]

    if len(matches) != 1:
        raise AutotaskTicketUpdateActivationError(
            "ticket update capability definition is not unique"
        )

    base = matches[0]
    metadata = dict(base.metadata)

    metadata.update(
        {
            "activation_state": (
                "ticket_update_mcp_source_only_not_activated"
            ),
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": (
                "true"
            ),
            "pilot_scope": "aot_owner_organization_scope",
            "safe_update_fields": ",".join(
                sorted(SAFE_TICKET_UPDATE_FIELDS)
            ),
            "ticket_work_start_policy": "standing_owner_approved",
            "ticket_work_start_queue": "Jason",
            "ticket_work_start_status": "In Progress",
            "ticket_work_start_work_type": "Remote Support",
            "ticket_work_start_trigger": (
                "first_ticket_specific_diagnostic_remediation_or_verification"
            ),
            "ticket_work_start_online_policy": (
                "endpoint_ticket_requires_device_online_evidence"
            ),
            "ticket_work_handoff_policy": (
                "restore_trusted_preclaim_queue_and_status_when_human_handoff_required"
            ),
            "ticket_work_reclaim_policy": (
                "block_reclaim_until_blocker_fingerprint_changes"
            ),
            "ticket_work_start_device_policy": (
                "preserve_existing_or_exact_drmm_uid_to_active_autotask_configuration"
            ),
            "ticket_work_start_classification_policy": (
                "preserve_existing_or_apply_explicit_triage_labels"
            ),
        }
    )

    evidence = CapabilityEvidence(
        required=True,
        requirements=(
            "authenticated requester identity",
            "provider requester authorization evidence",
            "exact resolved target ticket",
            "provider mutation result",
            "post-mutation ticket readback",
        ),
        verification_requirements=(
            "requester maps to exactly one active Autotask Resource",
            "provider-native requester impersonation is applied",
            "requester Autotask permissions permit Ticket update",
            "only explicitly allowed ticket fields are mutated",
            "post-mutation readback matches every intended field",
        ),
    )

    return replace(
        base,
        business_purpose=(
            "Apply one bounded update to an exact Autotask service ticket, "
            "including Jason's standing ticket-work-start lifecycle claim."
        ),
        client_isolation_required=False,
        evidence=evidence,
        metadata=metadata,
    )


def _ticket_update_provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        display_name="Autotask PSA Governed Ticket Update",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SERVICE_TICKET_UPDATE}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(
            structured_output=True,
        ),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Permit one narrowly governed Autotask ticket "
                "update through requester impersonation."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider-native requester authorization cannot be proven.",
                "A safer approved mutation capability replaces this pilot.",
            ),
            vendor_change_sources=(
                "Autotask REST API documentation",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "autotask",
            "resource_authority": "service_management",
            "write_capability": "true",
            "mutation_scope": "ticket_update_safe_fields_only",
            "provider_native_impersonation_required": "true",
            "activation_state": (
                "ticket_update_mcp_source_only_not_activated"
            ),
        },
    )


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field} must be a positive integer"
        ) from error

    if result < 1:
        raise ValueError(f"{field} must be a positive integer")

    return result


def _normalized_due(value: Any) -> str:
    text = str(value or "").strip()

    if not text or len(text) > 128:
        raise ValueError(
            "dueDateTime must be a bounded non-empty datetime string"
        )

    return text


class AutotaskTicketUpdateConnector(AutotaskMutationConnector):
    def __init__(self, *, autonomy_api_resource_id: int | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if autonomy_api_resource_id is not None:
            if isinstance(autonomy_api_resource_id, bool):
                raise ValueError("AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_INVALID")
            try:
                parsed = int(autonomy_api_resource_id)
            except (TypeError, ValueError) as error:
                raise ValueError("AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_INVALID") from error
            if parsed < 1:
                raise ValueError("AUTOTASK_TICKET_UPDATE_AUTONOMY_RESOURCE_ID_INVALID")
            self._autonomy_api_resource_id = parsed
        else:
            self._autonomy_api_resource_id = None

    def _is_autonomous_api_user_request(self, request: ConnectorRequest) -> bool:
        return (
            request.context.principal_id == AUTOTASK_TICKET_UPDATE_AUTONOMY_PRINCIPAL
            and self._autonomy_api_resource_id is not None
        )

    capabilities = frozenset(
        {
            "autotask.ticket.update",
        }
    )

    @staticmethod
    def _label_requires_resolution(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        try:
            return int(text) < 1
        except ValueError:
            return True

    @staticmethod
    def _ticket_fields(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            item = payload.get("item")
            if isinstance(item, Mapping):
                fields = item.get("fields")
        if not isinstance(fields, list):
            raise ValueError("AUTOTASK_TICKET_FIELD_METADATA_INVALID")
        return [field for field in fields if isinstance(field, Mapping)]

    @classmethod
    def _picklist_value_for_label(
        cls,
        *,
        fields_payload: Mapping[str, Any],
        field_name: str,
        label: str,
        parent_value: int | None = None,
    ) -> int:
        fields = [
            field
            for field in cls._ticket_fields(fields_payload)
            if str(field.get("name") or "").strip().casefold()
            == field_name.casefold()
        ]
        if len(fields) != 1:
            raise ValueError("AUTOTASK_TICKET_PICKLIST_FIELD_NOT_UNIQUE")

        values = fields[0].get("picklistValues")
        if not isinstance(values, list):
            raise ValueError("AUTOTASK_TICKET_PICKLIST_METADATA_INVALID")

        normalized = label.strip().casefold()
        matches: list[int] = []
        for item in values:
            if not isinstance(item, Mapping):
                continue
            if item.get("isActive") is False:
                continue
            if str(item.get("label") or "").strip().casefold() != normalized:
                continue
            if parent_value is not None:
                parent = item.get("parentValue")
                if str(parent or "").strip() != str(parent_value):
                    continue
            try:
                value = int(item.get("value"))
            except (TypeError, ValueError):
                continue
            if value > 0:
                matches.append(value)

        unique = sorted(set(matches))
        if len(unique) != 1:
            raise ValueError("AUTOTASK_TICKET_PICKLIST_LABEL_NOT_UNIQUE")
        return unique[0]

    def _provider_resolution_context(
        self,
        request: ConnectorRequest,
    ) -> tuple[Any, dict[str, str]]:
        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )
        prepared = AutotaskConnector.prepare_request(
            self,
            request,
            credentials,
        )
        headers = dict(prepared.headers)
        if self._is_autonomous_api_user_request(request):
            headers.pop("ImpersonationResourceId", None)
            self._preflight_requester_access(
                prepared=prepared,
                headers=headers,
                operation=request.context.capability,
            )
            return prepared, headers
        email = self._trusted_email(request)
        if email is None:
            raise PermissionError(
                "AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED"
            )
        resource_id = self._resolve_impersonation_resource_id(
            prepared=prepared,
            email=email,
        )
        headers["ImpersonationResourceId"] = str(resource_id)
        return prepared, headers

    def _resolve_work_type_label(
        self,
        *,
        prepared,
        headers: Mapping[str, str],
        label: str,
    ) -> int:
        search = {
            "filter": [
                {
                    "op": "eq",
                    "field": "name",
                    "value": label.strip(),
                }
            ],
            "MaxRecords": 10,
        }
        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/BillingCodes/query",
            headers=headers,
            params={
                "search": json.dumps(
                    search,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            },
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(payload, Mapping):
            raise ValueError("AUTOTASK_WORK_TYPE_LOOKUP_INVALID")
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("AUTOTASK_WORK_TYPE_LOOKUP_INVALID")

        normalized = label.strip().casefold()
        matches: list[int] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("name") or "").strip().casefold() != normalized:
                continue
            if item.get("isActive") is not True:
                continue
            try:
                use_type = int(item.get("useType"))
                item_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            if use_type == 1 and item_id > 0:
                matches.append(item_id)

        unique = sorted(set(matches))
        if len(unique) != 1:
            raise ValueError("AUTOTASK_WORK_TYPE_LABEL_NOT_UNIQUE")
        return unique[0]

    def _resolve_symbolic_payload(
        self,
        request: ConnectorRequest,
    ) -> dict[str, Any]:
        raw = request.arguments.get("payload")
        if not isinstance(raw, Mapping):
            raise ValueError("ticket update requires a structured payload")
        payload = dict(raw)

        picklist_labels = {
            field: str(payload[field]).strip()
            for field in _TICKET_PICKLIST_LABEL_FIELDS
            if field in payload
            and self._label_requires_resolution(payload[field])
        }
        work_type_label = None
        if (
            "billingCodeID" in payload
            and self._label_requires_resolution(payload["billingCodeID"])
        ):
            work_type_label = str(payload["billingCodeID"]).strip()

        if not picklist_labels and work_type_label is None:
            return payload

        prepared, headers = self._provider_resolution_context(request)

        fields_payload = None
        if picklist_labels:
            fields_payload = self._transport.request(
                method="GET",
                url=(
                    f"{self._api_root(prepared)}/V1.0/"
                    "Tickets/entityInformation/fields"
                ),
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=prepared.timeout_seconds,
            )
            if not isinstance(fields_payload, Mapping):
                raise ValueError("AUTOTASK_TICKET_FIELD_METADATA_INVALID")

            for field in ("status", "queueID", "ticketType", "issueType"):
                label = picklist_labels.get(field)
                if label is None:
                    continue
                payload[field] = self._picklist_value_for_label(
                    fields_payload=fields_payload,
                    field_name=field,
                    label=label,
                )

            sub_label = picklist_labels.get("subIssueType")
            if sub_label is not None:
                issue_value = payload.get("issueType")
                if isinstance(issue_value, str):
                    try:
                        issue_value = int(issue_value)
                    except ValueError as error:
                        raise ValueError(
                            "AUTOTASK_SUBISSUE_REQUIRES_RESOLVED_ISSUE"
                        ) from error
                if isinstance(issue_value, bool) or not isinstance(issue_value, int):
                    raise ValueError(
                        "AUTOTASK_SUBISSUE_REQUIRES_RESOLVED_ISSUE"
                    )
                payload["subIssueType"] = self._picklist_value_for_label(
                    fields_payload=fields_payload,
                    field_name="subIssueType",
                    label=sub_label,
                    parent_value=issue_value,
                )

        if work_type_label is not None:
            payload["billingCodeID"] = self._resolve_work_type_label(
                prepared=prepared,
                headers=headers,
                label=work_type_label,
            )

        return payload

    @staticmethod
    def validated_payload(
        request: ConnectorRequest,
    ) -> dict[str, Any]:
        raw = request.arguments.get("payload")

        if not isinstance(raw, Mapping):
            raise ValueError(
                "ticket update requires a structured payload"
            )

        payload = dict(raw)

        ticket_id = _positive_int(
            payload.get("id"),
            field="id",
        )

        supplied = set(payload) - {"id"}

        if not supplied:
            raise ValueError(
                "ticket update requires at least one mutable field"
            )

        disallowed = supplied - SAFE_TICKET_UPDATE_FIELDS

        if disallowed:
            raise PermissionError(
                "AUTOTASK_TICKET_UPDATE_FIELD_NOT_ALLOWED"
            )

        normalized: dict[str, Any] = {
            "id": ticket_id,
        }

        for field in supplied:
            value = payload[field]

            if field in _INTEGER_FIELDS:
                normalized[field] = _positive_int(
                    value,
                    field=field,
                )
            elif field == "dueDateTime":
                normalized[field] = _normalized_due(value)

        return normalized

    def _readback(
        self,
        *,
        request: ConnectorRequest,
        ticket_id: int,
    ) -> Mapping[str, Any]:
        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )

        read_request = ConnectorRequest(
            context=ConnectorContext(
                correlation_id=request.context.correlation_id,
                principal_id=request.context.principal_id,
                organization_id=request.context.organization_id,
                client_id=request.context.client_id,
                capability="autotask.ticket.get",
                mode="observe",
            ),
            arguments={
                "ticket_id": ticket_id,
            },
        )

        prepared = AutotaskConnector.prepare_request(
            self,
            read_request,
            credentials,
        )

        headers = dict(prepared.headers)
        if self._is_autonomous_api_user_request(request):
            if self._autonomy_api_resource_id is None:
                raise AutotaskTicketUpdateVerificationError(
                    "autonomous API-user resource id unavailable for readback"
                )
            headers.pop("ImpersonationResourceId", None)
        else:
            email = self._trusted_email(request)
            if email is None:
                raise AutotaskTicketUpdateVerificationError(
                    "trusted requester binding unavailable for readback"
                )
            resource_id = self._resolve_impersonation_resource_id(
                prepared=prepared,
                email=email,
            )
            headers["ImpersonationResourceId"] = str(resource_id)

        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )

        if not isinstance(payload, Mapping):
            raise AutotaskTicketUpdateVerificationError(
                "ticket readback was not a mapping"
            )

        item = payload.get("item")

        if isinstance(item, Mapping):
            return item

        return payload

    @staticmethod
    def _verify(
        *,
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> None:
        observed_id = _positive_int(
            observed.get("id"),
            field="observed id",
        )

        if observed_id != expected["id"]:
            raise AutotaskTicketUpdateVerificationError(
                "ticket id failed readback"
            )

        for field, expected_value in expected.items():
            if field == "id":
                continue

            observed_value = observed.get(field)

            if field in _INTEGER_FIELDS:
                try:
                    observed_value = int(observed_value)
                except (TypeError, ValueError) as error:
                    raise AutotaskTicketUpdateVerificationError(
                        f"{field} readback was invalid"
                    ) from error

            if field == "dueDateTime":
                observed_value = str(
                    observed_value or ""
                ).strip()

            if observed_value != expected_value:
                raise AutotaskTicketUpdateVerificationError(
                    f"{field} failed readback"
                )

    def prepare_governed_execution(
        self,
        request: ConnectorRequest,
    ) -> ProviderPreparedExecution:
        if request.context.capability != "autotask.ticket.update":
            raise ConnectorAuthorizationError(
                "ticket-update connector exposes only Ticket update"
            )

        raw = request.arguments.get("payload")
        if not isinstance(raw, Mapping):
            raise ValueError("ticket update requires a structured payload")
        raw_payload = dict(raw)
        resolved_payload = self._resolve_symbolic_payload(request)
        normalized_input = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": resolved_payload},
        )
        expected = self.validated_payload(normalized_input)
        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": expected},
        )

        symbolic_resolutions: dict[str, Any] = {}
        for field in (*_TICKET_PICKLIST_LABEL_FIELDS, "billingCodeID"):
            if field not in raw_payload or not self._label_requires_resolution(raw_payload[field]):
                continue
            symbolic_resolutions[field] = {
                "symbolic": str(raw_payload[field]).strip(),
                "resolved": expected[field],
            }

        if normalized_request.context.mode != "execute":
            raise ConnectorAuthorizationError("Autotask mutation requires explicit execute mode.")
        if not autotask_mutation_execution_enabled():
            raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
        credentials = self._secrets.resolve(self.logical_secret, normalized_request.context)
        prepared = AutotaskMutationConnector.prepare_request(
            self, normalized_request, credentials
        )
        relative_path = prepared.audit_operation or urlsplit(prepared.url).path
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method=prepared.method,
            resource_type="service_ticket",
            resource_identifier=str(expected["id"]),
            normalized_path=relative_path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions=symbolic_resolutions,
            opaque=_PreparedAutotaskTicketUpdate(
                request=normalized_request, expected=dict(expected), prepared=prepared
            ),
        )

    def execute_governed_execution(
        self,
        prepared_execution: ProviderPreparedExecution,
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedAutotaskTicketUpdate):
            raise PermissionError("invalid Autotask ticket-update prepared execution")
        request = opaque.request
        expected = dict(opaque.expected)
        prepared = opaque.prepared
        if prepared_execution.provider_capability != request.context.capability:
            raise PermissionError("prepared Autotask provider capability no longer matches authorized execution plan")
        if str(prepared.method).strip().upper() != str(prepared_execution.action_method).strip().upper():
            raise PermissionError("prepared Autotask method no longer matches authorized execution plan")
        observed_path = normalize_provider_relative_path(
            prepared.audit_operation or urlsplit(prepared.url).path
        )
        if observed_path != normalize_provider_relative_path(prepared_execution.normalized_path):
            raise PermissionError("prepared Autotask path no longer matches authorized execution plan")
        if str(expected["id"]) != str(prepared_execution.resource_identifier):
            raise PermissionError("prepared Autotask target no longer matches authorized execution plan")
        if dict(prepared.json or {}) != dict(prepared_execution.payload):
            raise PermissionError("prepared Autotask payload no longer matches authorized execution plan")
        if dict(prepared.params or {}) != dict(prepared_execution.parameters):
            raise PermissionError("prepared Autotask parameters no longer match authorized execution plan")

        if request.context.mode != "execute":
            raise ConnectorAuthorizationError("Autotask mutation requires explicit execute mode.")
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            if not autotask_mutation_execution_enabled():
                raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
            payload = self._transport.request(
                method=prepared.method,
                url=prepared.url,
                headers=prepared.headers,
                params=prepared.params,
                json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as error:
            self._audit_mutation_event(
                "connector.mutation.failed", request, error_type=type(error).__name__
            )
            raise
        self._audit_mutation_event("connector.mutation.completed", request)
        result = ConnectorResult(
            capability=request.context.capability, provider=self.provider_name, data=payload
        )
        return self._verified_result(request=request, expected=expected, result=result)

    def _verified_result(
        self,
        *,
        request: ConnectorRequest,
        expected: Mapping[str, Any],
        result: ConnectorResult,
    ) -> ConnectorResult:
        try:
            observed = self._readback(
                request=request,
                ticket_id=expected["id"],
            )
            self._verify(expected=expected, observed=observed)
        except Exception as error:
            self._audit.record(
                "connector.mutation.verification_failed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "error_type": type(error).__name__,
                },
            )
            if isinstance(error, AutotaskTicketUpdateVerificationError):
                raise
            raise AutotaskTicketUpdateVerificationError(
                "ticket update post-mutation verification failed"
            ) from error

        self._audit.record(
            "connector.mutation.verified",
            request.context,
            {
                "provider": self.provider_name,
                "capability": request.context.capability,
                "ticket_id": expected["id"],
            },
        )
        data = dict(result.data)
        data["jasonVerification"] = {
            "readbackVerified": True,
            "ticketId": expected["id"],
            "verifiedFields": sorted(key for key in expected if key != "id"),
        }
        return ConnectorResult(
            capability=result.capability,
            provider=result.provider,
            data=data,
            evidence_ids=(*result.evidence_ids, f"autotask:ticket:{expected['id']}"),
            warnings=result.warnings,
        )

    def execute(
        self,
        request: ConnectorRequest,
    ) -> ConnectorResult:
        if request.context.capability != "autotask.ticket.update":
            raise ConnectorAuthorizationError(
                "ticket-update connector exposes only Ticket update"
            )
        resolved_payload = self._resolve_symbolic_payload(request)
        normalized_input = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": resolved_payload},
        )
        expected = self.validated_payload(normalized_input)
        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": expected},
        )
        result = super().execute(normalized_request)
        return self._verified_result(request=request, expected=expected, result=result)



def _validate_pre_activation_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    capability = capabilities.get(
        capability_name=SERVICE_TICKET_UPDATE,
        version="1.0",
    )

    provider = providers.get(
        AUTOTASK_TICKET_UPDATE_PROVIDER
    )

    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise AutotaskTicketUpdateActivationError(
            "ticket update capability is not BUILDING"
        )

    if capability.approval.required is not True:
        raise AutotaskTicketUpdateActivationError(
            "ticket update unexpectedly lacks approval"
        )

    if capability.idempotency_key_required is not True:
        raise AutotaskTicketUpdateActivationError(
            "ticket update unexpectedly lacks idempotency"
        )

    if capability.maximum_attempts != 1:
        raise AutotaskTicketUpdateActivationError(
            "ticket update permits provider retry"
        )

    if capability.client_isolation_required:
        raise AutotaskTicketUpdateActivationError(
            "Owner pilot unexpectedly requires client-bound identity"
        )

    if (
        str(
            capability.metadata.get(
                "mcp_action_enabled",
                "",
            )
        ).casefold()
        != "true"
    ):
        raise AutotaskTicketUpdateActivationError(
            "ticket update MCP action flag missing"
        )

    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider is not PLANNED"
        )

    if provider.approval_status is not ProviderApproval.PILOT:
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider approval drifted"
        )

    if provider.capabilities != frozenset(
        {
            SERVICE_TICKET_UPDATE,
        }
    ):
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider capability scope drifted"
        )


def apply_autotask_ticket_update_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> AutotaskTicketUpdateActivationState:
    normalized = str(
        profile or ""
    ).strip().casefold()

    if not normalized:
        return AutotaskTicketUpdateActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if normalized != AUTOTASK_TICKET_UPDATE_PROFILE:
        raise AutotaskTicketUpdateActivationError(
            "unsupported Autotask ticket-update MCP profile"
        )

    if not autotask_ticket_update_mcp_surface_enabled():
        raise AutotaskTicketUpdateActivationError(
            "ticket-update MCP profile requires mutation "
            "execution gate"
        )

    _validate_pre_activation_contract(
        capabilities=capabilities,
        providers=providers,
    )

    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_UPDATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    providers.set_approval(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )

    providers.set_health(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )

    providers.set_lifecycle(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    return AutotaskTicketUpdateActivationState(
        profile=normalized,
        enabled=True,
        provider_ids=(
            AUTOTASK_TICKET_UPDATE_PROVIDER,
        ),
        capability_names=(
            SERVICE_TICKET_UPDATE,
        ),
    )


def register_autotask_ticket_update_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutotaskTicketUpdateActivationState:
    capabilities.register(
        _ticket_update_definition(
            now=now,
        )
    )

    providers.register(
        _ticket_update_provider(
            now=now,
        )
    )

    return apply_autotask_ticket_update_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(
            AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
            "",
        ),
    )


def build_autotask_ticket_update_invoker(
    *,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: HttpTransport,
    audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )

    connector = AutotaskTicketUpdateConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        bindings=bindings,
        autonomy_api_resource_id=(
            configured_autotask_ticket_update_autonomy_resource_id()
        ),
    )

    return GovernedConnectorCapabilityInvoker(
        connectors={
            AUTOTASK_TICKET_UPDATE_PROVIDER: connector,
        },
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )


def register_autotask_ticket_update_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(
        SERVICE_TICKET_UPDATE,
        invoker,
    )
