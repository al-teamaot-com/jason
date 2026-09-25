from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PurePath
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
    autotask_mutation_execution_enabled,
)
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
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
    SERVICE_TICKET_ATTACHMENT_CREATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker

AUTOTASK_TICKET_ATTACHMENT_PROVIDER = "autotask_ticket_attachment"
AUTOTASK_TICKET_ATTACHMENT_PROFILE_ENV = "JASON_AUTOTASK_TICKET_ATTACHMENT_MCP_PROFILE"
AUTOTASK_TICKET_ATTACHMENT_PROFILE = "owner-ticket-attachment-v1"
MAX_ATTACHMENT_BYTES = 6_000_000


class AutotaskTicketAttachmentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AutotaskTicketAttachmentActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PreparedAttachment:
    request: ConnectorRequest
    prepared: PreparedRequest
    company_id: int
    ticket_id: int
    attachment_sha256: str
    attachment_size: int
    publish: int


def _definition(now: datetime):
    matches = [
        item
        for item in autotask_mutation_capability_definitions(now=now)
        if item.capability_name == SERVICE_TICKET_ATTACHMENT_CREATE
    ]
    if len(matches) != 1:
        raise AutotaskTicketAttachmentError("attachment capability catalog incomplete")
    base = matches[0]
    metadata = dict(base.metadata)
    metadata.update(
        {
            "activation_state": "ticket_attachment_source_only_not_activated",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_owner_ticket_attachment_internal_only",
            "provider_credential": "autotask.write",
            "attachment_visibility": "internal_only",
            "attachment_max_bytes": str(MAX_ATTACHMENT_BYTES),
            "execution_plan_content_policy": "digest_and_size_only_no_file_bytes",
        }
    )
    # Owner pilot remains organization scoped, as do the proven ticket/note write
    # pilots. The connector independently proves ticket.companyID == company_id.
    return replace(base, client_isolation_required=False, metadata=metadata)


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_TICKET_ATTACHMENT_PROVIDER,
        display_name="Autotask Governed Ticket Attachments",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SERVICE_TICKET_ATTACHMENT_CREATE}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=1,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Attach bounded evidence files to verified Autotask tickets.",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Provider attachment authorization cannot be proven.",),
            vendor_change_sources=("Autotask REST API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "autotask",
            "write_capability": "true",
            "provider_native_impersonation_required": "true",
            "activation_state": "ticket_attachment_source_only_not_activated",
            "raw_attachment_bytes_in_audit": "false",
        },
    )


class AutotaskTicketAttachmentConnector(AutotaskMutationConnector):
    logical_secret = "autotask.write"
    capabilities = frozenset({"autotask.ticket.attachment.create"})
    operation_preflight = {
        "autotask.ticket.attachment.create": (
            "TicketAttachments",
            "userAccessForCreate",
        )
    }

    @staticmethod
    def _positive(value: Any, name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if result < 1:
            raise ValueError(f"{name} must be a positive integer")
        return result

    @staticmethod
    def _decode_data(value: Any) -> bytes:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("attachment data_base64 is required")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("attachment data_base64 is invalid") from exc
        if not decoded:
            raise ValueError("attachment file must not be empty")
        if len(decoded) > MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment exceeds the 6000000-byte Jason limit")
        return decoded

    @staticmethod
    def _filename(value: Any) -> str:
        name = str(value or "").strip()
        if not name or len(name) > 255 or "\x00" in name:
            raise ValueError("attachment file_name is invalid")
        if PurePath(name).name != name or "/" in name or "\\" in name:
            raise ValueError("attachment file_name must be a basename")
        return name

    @staticmethod
    def _title(value: Any, filename: str) -> str:
        title = str(value or "").strip() or filename
        if len(title) > 250:
            raise ValueError("attachment title exceeds 250 characters")
        return title

    @staticmethod
    def _item(data: Mapping[str, Any]) -> Mapping[str, Any]:
        item = data.get("item")
        if isinstance(item, Mapping):
            return item
        items = data.get("items")
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], Mapping):
            return items[0]
        return data

    def _requester_headers(self, request: ConnectorRequest, prepared: PreparedRequest) -> Mapping[str, str]:
        email = self._trusted_email(request)
        if email is None:
            raise PermissionError("AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED")
        resource_id = self._resolve_impersonation_resource_id(prepared=prepared, email=email)
        headers = dict(prepared.headers)
        headers["ImpersonationResourceId"] = str(resource_id)
        return headers

    def _verify_ticket_company(
        self,
        *,
        prepared: PreparedRequest,
        headers: Mapping[str, str],
        company_id: int,
        ticket_id: int,
    ) -> None:
        search = json.dumps(
            {
                "MaxRecords": 2,
                "filter": [{"op": "eq", "field": "id", "value": ticket_id}],
            },
            separators=(",", ":"), sort_keys=True,
        )
        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/Tickets/query",
            headers=headers,
            params={"search": search},
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(payload, Mapping):
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_READ_INVALID")
        item = self._item(payload)
        try:
            observed_id = int(item.get("id"))
            observed_company = int(item.get("companyID"))
        except (TypeError, ValueError) as exc:
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_SCOPE_INVALID") from exc
        if observed_id != ticket_id or observed_company != company_id:
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_COMPANY_MISMATCH")

    def _resolve_internal_publish(
        self,
        *,
        prepared: PreparedRequest,
        headers: Mapping[str, str],
    ) -> int:
        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/TicketAttachments/entityInformation/fields",
            headers=headers,
            params=None,
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        fields = payload.get("fields") if isinstance(payload, Mapping) else None
        if not isinstance(fields, list):
            raise PermissionError("AUTOTASK_ATTACHMENT_PUBLISH_METADATA_INVALID")
        publish_fields = [
            field for field in fields
            if isinstance(field, Mapping)
            and str(field.get("name") or "").strip().casefold() == "publish"
        ]
        if len(publish_fields) != 1:
            raise PermissionError("AUTOTASK_ATTACHMENT_PUBLISH_METADATA_INVALID")
        values = publish_fields[0].get("picklistValues")
        if not isinstance(values, list):
            raise PermissionError("AUTOTASK_ATTACHMENT_PUBLISH_METADATA_INVALID")
        matches: list[int] = []
        for item in values:
            if not isinstance(item, Mapping):
                continue
            label = " ".join(str(item.get("label") or "").strip().casefold().split())
            if label not in {"internal users only", "internal only"}:
                continue
            try:
                matches.append(int(item.get("value")))
            except (TypeError, ValueError):
                continue
        unique = sorted(set(matches))
        if len(unique) != 1:
            raise PermissionError("AUTOTASK_ATTACHMENT_INTERNAL_VISIBILITY_NOT_UNIQUE")
        return unique[0]

    def _normalize(self, request: ConnectorRequest) -> tuple[ConnectorRequest, int, int, str, bytes, str]:
        if request.context.capability not in self.capabilities:
            raise ConnectorAuthorizationError("attachment connector exposes only ticket attachment create")
        company_id = self._positive(request.arguments.get("company_id"), "company_id")
        ticket_id = self._positive(request.arguments.get("ticket_id"), "ticket_id")
        filename = self._filename(request.arguments.get("file_name"))
        content = self._decode_data(request.arguments.get("data_base64"))
        title = self._title(request.arguments.get("title"), filename)
        visibility = str(request.arguments.get("visibility") or "internal").strip().casefold()
        if visibility != "internal":
            raise PermissionError("attachment pilot permits internal visibility only")
        normalized = ConnectorRequest(
            context=request.context,
            arguments={
                "company_id": company_id,
                "ticket_id": ticket_id,
                "file_name": filename,
                "title": title,
                "visibility": visibility,
                "data_base64": base64.b64encode(content).decode("ascii"),
            },
        )
        return normalized, company_id, ticket_id, filename, content, title

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        normalized, company_id, ticket_id, filename, content, title = self._normalize(request)
        if normalized.context.mode != "execute":
            raise ConnectorAuthorizationError("Autotask mutation requires explicit execute mode")
        if not autotask_mutation_execution_enabled():
            raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
        credentials = self._secrets.resolve(self.logical_secret, normalized.context)
        seed_payload = {
            "attachedByContactID": None,
            "attachedByResourceID": None,
            "attachmentType": "FILE_ATTACHMENT",
            "fullPath": filename,
            "publish": 0,
            "title": title,
            "data": normalized.arguments["data_base64"],
        }
        provider_request = ConnectorRequest(
            context=normalized.context,
            arguments={"ticketID": ticket_id, "payload": seed_payload},
        )
        seed = AutotaskConnector.prepare_request(self, provider_request, credentials)
        headers = self._requester_headers(normalized, seed)
        self._preflight_requester_access(
            prepared=seed,
            headers=headers,
            operation="autotask.ticket.attachment.create",
        )
        self._verify_ticket_company(
            prepared=seed, headers=headers, company_id=company_id, ticket_id=ticket_id
        )
        publish = self._resolve_internal_publish(prepared=seed, headers=headers)
        payload = {**seed_payload, "publish": publish}
        prepared = replace(seed, headers=headers, json=payload)
        digest = hashlib.sha256(content).hexdigest()
        manifest = {
            "company_id": company_id,
            "ticket_id": ticket_id,
            "file_name": filename,
            "title": title,
            "visibility": "internal",
            "publish": publish,
            "sha256": digest,
            "size_bytes": len(content),
        }
        return ProviderPreparedExecution(
            provider_capability="autotask.ticket.attachment.create",
            action_method="POST",
            resource_type="service_ticket_attachment",
            resource_identifier=str(ticket_id),
            normalized_path=seed.audit_operation or urlsplit(seed.url).path,
            payload=manifest,
            parameters={"company_id": company_id, "ticket_id": ticket_id},
            symbolic_resolutions={"visibility": str(publish)},
            opaque=_PreparedAttachment(
                request=normalized,
                prepared=prepared,
                company_id=company_id,
                ticket_id=ticket_id,
                attachment_sha256=digest,
                attachment_size=len(content),
                publish=publish,
            ),
        )

    @staticmethod
    def _created_id(data: Mapping[str, Any]) -> int:
        for key in ("itemId", "itemID", "id"):
            raw = data.get(key)
            if raw is not None and not isinstance(raw, bool) and str(raw).isdigit() and int(raw) > 0:
                return int(raw)
        raise AutotaskTicketAttachmentError("created attachment id missing")

    def execute_governed_execution(self, prepared_execution: ProviderPreparedExecution) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedAttachment):
            raise PermissionError("invalid attachment prepared execution")
        request = opaque.request
        prepared = opaque.prepared
        if prepared_execution.provider_capability != "autotask.ticket.attachment.create":
            raise PermissionError("attachment provider capability changed")
        if prepared_execution.resource_identifier != str(opaque.ticket_id):
            raise PermissionError("attachment target ticket changed")
        if normalize_provider_relative_path(prepared_execution.normalized_path) != normalize_provider_relative_path(prepared.audit_operation or urlsplit(prepared.url).path):
            raise PermissionError("attachment provider path changed")
        provider_payload = dict(prepared.json or {})
        content = self._decode_data(provider_payload.get("data"))
        manifest = dict(prepared_execution.payload)
        observed_manifest = {
            "company_id": opaque.company_id,
            "ticket_id": opaque.ticket_id,
            "file_name": str(provider_payload.get("fullPath") or ""),
            "title": str(provider_payload.get("title") or ""),
            "visibility": "internal",
            "publish": int(provider_payload.get("publish")),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        if observed_manifest != manifest:
            raise PermissionError("attachment manifest no longer matches authorized execution plan")
        if dict(prepared_execution.parameters) != {"company_id": opaque.company_id, "ticket_id": opaque.ticket_id}:
            raise PermissionError("attachment execution parameters changed")
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            if not autotask_mutation_execution_enabled():
                raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
            provider_data = self._transport.request(
                method=prepared.method,
                url=prepared.url,
                headers=prepared.headers,
                params=prepared.params,
                json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as exc:
            self._audit_mutation_event(
                "connector.mutation.failed", request, error_type=type(exc).__name__
            )
            raise
        self._audit_mutation_event("connector.mutation.completed", request)
        if not isinstance(provider_data, Mapping):
            raise AutotaskTicketAttachmentError("attachment create response invalid")
        attachment_id = self._created_id(provider_data)
        readback = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/Tickets/{opaque.ticket_id}/Attachments/{attachment_id}",
            headers=prepared.headers,
            params=None,
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(readback, Mapping):
            raise AutotaskTicketAttachmentError("attachment readback invalid")
        item = self._item(readback)
        try:
            observed_id = int(item.get("id"))
            observed_ticket = int(item.get("ticketID"))
            observed_publish = int(item.get("publish"))
        except (TypeError, ValueError) as exc:
            raise AutotaskTicketAttachmentError("attachment readback identity invalid") from exc
        observed_data = self._decode_data(item.get("data"))
        if (
            observed_id != attachment_id
            or observed_ticket != opaque.ticket_id
            or observed_publish != opaque.publish
            or str(item.get("fullPath") or "") != manifest["file_name"]
            or str(item.get("title") or "") != manifest["title"]
            or hashlib.sha256(observed_data).hexdigest() != opaque.attachment_sha256
            or len(observed_data) != opaque.attachment_size
        ):
            raise AutotaskTicketAttachmentError("attachment post-write verification mismatch")
        sanitized = {
            "itemId": attachment_id,
            "jasonVerification": {
                "readbackVerified": True,
                "ticketId": opaque.ticket_id,
                "companyId": opaque.company_id,
                "fileName": manifest["file_name"],
                "sha256": opaque.attachment_sha256,
                "sizeBytes": opaque.attachment_size,
                "visibility": "internal",
            },
        }
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=sanitized,
            evidence_ids=(f"autotask:ticket-attachment:{attachment_id}",),
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(self.prepare_governed_execution(request))


def register_autotask_ticket_attachment_runtime_foundation(
    *, capabilities: CapabilityRegistryService, providers: ExecutionProviderRegistryService, now: datetime
) -> AutotaskTicketAttachmentActivationState:
    capabilities.register(_definition(now))
    providers.register(_provider(now))
    profile = os.getenv(AUTOTASK_TICKET_ATTACHMENT_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return AutotaskTicketAttachmentActivationState("", False, (), ())
    if profile != AUTOTASK_TICKET_ATTACHMENT_PROFILE:
        raise AutotaskTicketAttachmentError("unsupported attachment MCP profile")
    if os.getenv(AUTOTASK_MUTATION_ENABLED_ENV, "").strip().casefold() != "true":
        raise AutotaskTicketAttachmentError("attachment profile requires mutation gate")
    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_ATTACHMENT_CREATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=AUTOTASK_TICKET_ATTACHMENT_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_TICKET_ATTACHMENT_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_TICKET_ATTACHMENT_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return AutotaskTicketAttachmentActivationState(
        profile, True, (AUTOTASK_TICKET_ATTACHMENT_PROVIDER,),
        (SERVICE_TICKET_ATTACHMENT_CREATE,),
    )


def build_autotask_ticket_attachment_invoker(
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
    connector = AutotaskTicketAttachmentConnector(
        secrets=secrets, transport=transport, audit=audit, bindings=bindings,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_TICKET_ATTACHMENT_PROVIDER: connector},
        provider_capability_map={
            (AUTOTASK_TICKET_ATTACHMENT_PROVIDER, SERVICE_TICKET_ATTACHMENT_CREATE):
                "autotask.ticket.attachment.create"
        },
    )


def register_autotask_ticket_attachment_invoker(
    *, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker
) -> None:
    invokers.register(SERVICE_TICKET_ATTACHMENT_CREATE, invoker)
