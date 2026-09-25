from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass, replace
from typing import Any, Mapping, Protocol

from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorRequest

from .connector import AutotaskConnector


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


AUTOTASK_REQUESTER_AUTH_MODE_ENV = "JASON_AUTOTASK_REQUESTER_AUTH_MODE"
AUTOTASK_AUTH_MODE_IMPERSONATED = "impersonated"
AUTOTASK_AUTH_MODE_JASON_MANAGED = "jason_managed"
_ALLOWED_AUTOTASK_REQUESTER_AUTH_MODES = frozenset(
    {
        AUTOTASK_AUTH_MODE_IMPERSONATED,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    }
)

# Restrict provider-native requester impersonation to canonical provider
# operations whose Autotask entities are documented as supporting
# impersonation/query security. The temporary Jason-managed mode below does not
# add this header and relies on the already-proven Jason authority context plus
# information-release authorization instead.
_IMPERSONATED_READ_OPERATIONS = frozenset(
    {
        "autotask.company.get",
        "autotask.company.search",
        "autotask.ticket.get",
        "autotask.ticket.search",
        "autotask.ticket.count",
    }
)


def autotask_requester_authorization_mode() -> str:
    """Return the explicit Autotask requester-authorization mode.

    Jason-managed authorization is the temporary production default while the
    provider-native impersonation path is blocked by an Autotask HTTP 500. The
    legacy impersonated path remains available for bounded diagnostics and
    rollback. Unknown values fail closed before a provider request is prepared.
    """

    mode = os.getenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    ).strip().casefold()
    if mode not in _ALLOWED_AUTOTASK_REQUESTER_AUTH_MODES:
        raise RuntimeError("AUTOTASK_REQUESTER_AUTH_MODE_INVALID")
    return mode


@dataclass(frozen=True, slots=True)
class AutotaskImpersonationEvidence:
    applied: bool
    basis: str | None = None


class AutotaskImpersonatingConnector(AutotaskConnector):
    """Execute Autotask reads with an explicit requester-authorization mode.

    Autotask REST authentication always uses the dedicated API-only integration
    account. In ``impersonated`` mode, supported read entities resolve the
    already-authenticated Jason principal through the durable Microsoft binding,
    map that trusted email to exactly one Autotask Resource, and supply
    Autotask's ``ImpersonationResourceId`` header.

    In temporary ``jason_managed`` mode the provider request is intentionally
    executed only as the API service account. Requester authorization and
    release remain separate and are enforced by Jason's identity/authority,
    Central Orchestrator, and information-release boundary. This mode does not
    grant provider writes or bypass Jason authorization.

    Autotask environments may allow Ticket Query while denying the direct
    Ticket GET route. Jason therefore implements canonical ``ticket.read`` as a
    bounded exact query. Numeric identifiers query ``id``; human Autotask
    ticket numbers query ``ticketNumber``. The outward provider capability
    remains ``autotask.ticket.get`` so the canonical governance contract does
    not change while the provider transport uses the proven read-only query
    path.

    Autotask ticket status is a tenant picklist backed by an integer value. A
    conversational selector such as ``New`` must therefore be resolved against
    the live Tickets entityInformation/fields metadata before it is sent in a
    query. Numeric status values remain pass-through and do not require the
    metadata lookup. Unknown or ambiguous labels fail closed before the ticket
    query.
    """

    def __init__(self, *, bindings: TrustedPrincipalBindingResolver | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bindings = bindings

    def _trusted_email(self, request: ConnectorRequest) -> str | None:
        if self._bindings is None:
            return None
        binding = self._bindings.find_active_by_jason_identity(
            jason_identity_id=request.context.principal_id
        )
        if binding is None:
            return None
        email = str(getattr(binding, "email_address", "") or "").strip().casefold()
        return email or None

    @staticmethod
    def _api_root(prepared: PreparedRequest) -> str:
        operation = str(prepared.audit_operation or "")
        if not operation or not prepared.url.endswith(operation):
            raise RuntimeError("Autotask prepared request did not expose a bounded API operation")
        return prepared.url[: -len(operation)].rstrip("/")

    @staticmethod
    def _ticket_read_search_value(value: Any) -> tuple[str, Any]:
        if value is None or isinstance(value, bool):
            raise ValueError("ticket_id must be a positive numeric id or ticket number")

        if isinstance(value, int):
            if value < 1:
                raise ValueError("ticket_id must be a positive numeric id or ticket number")
            return "id", value

        text = str(value).strip()
        if not text:
            raise ValueError("ticket_id must be a positive numeric id or ticket number")

        try:
            numeric = int(text)
        except ValueError:
            return "ticketNumber", text

        if numeric < 1:
            raise ValueError("ticket_id must be a positive numeric id or ticket number")
        return "id", numeric

    def _prepare_ticket_read_as_query(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        field, value = self._ticket_read_search_value(
            request.arguments.get("ticket_id")
        )
        search = json.dumps(
            {
                "MaxRecords": 2,
                "filter": [
                    {
                        "op": "eq",
                        "field": field,
                        "value": value,
                    }
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        query_request = ConnectorRequest(
            context=replace(
                request.context,
                capability="autotask.ticket.search",
            ),
            arguments={"search": search},
        )
        return super().prepare_request(query_request, credentials)

    @staticmethod
    def _status_picklist_values(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            item = payload.get("item")
            if isinstance(item, Mapping):
                fields = item.get("fields")
        if not isinstance(fields, list):
            raise ValueError("AUTOTASK_TICKET_STATUS_METADATA_INVALID")

        status_fields = [
            field
            for field in fields
            if isinstance(field, Mapping)
            and str(field.get("name") or "").strip().casefold() == "status"
        ]
        if len(status_fields) != 1:
            raise ValueError("AUTOTASK_TICKET_STATUS_METADATA_INVALID")

        picklist_values = status_fields[0].get("picklistValues")
        if not isinstance(picklist_values, list):
            raise ValueError("AUTOTASK_TICKET_STATUS_METADATA_INVALID")

        return [item for item in picklist_values if isinstance(item, Mapping)]

    def _resolve_ticket_status_label(
        self,
        *,
        prepared: PreparedRequest,
        label: str,
    ) -> int:
        normalized = label.strip().casefold()
        if not normalized:
            raise ValueError("AUTOTASK_TICKET_STATUS_LABEL_REQUIRED")

        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/Tickets/entityInformation/fields",
            headers=prepared.headers,
            params=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(payload, Mapping):
            raise ValueError("AUTOTASK_TICKET_STATUS_METADATA_INVALID")

        matches: list[int] = []
        for item in self._status_picklist_values(payload):
            candidate = str(item.get("label") or "").strip().casefold()
            if candidate != normalized:
                continue
            try:
                value = int(item.get("value"))
            except (TypeError, ValueError):
                continue
            matches.append(value)

        unique = sorted(set(matches))
        if len(unique) != 1:
            raise ValueError("AUTOTASK_TICKET_STATUS_LABEL_NOT_UNIQUE")
        return unique[0]

    def _resolve_ticket_search_status(
        self,
        *,
        prepared: PreparedRequest,
    ) -> PreparedRequest:
        if not isinstance(prepared.params, Mapping):
            return prepared
        raw_search = prepared.params.get("search")
        if not isinstance(raw_search, str) or not raw_search.strip():
            return prepared

        try:
            search = json.loads(raw_search)
        except ValueError:
            return prepared
        if not isinstance(search, Mapping):
            return prepared

        raw_filters = search.get("filter")
        if not isinstance(raw_filters, list):
            return prepared

        filters: list[Any] = []
        changed = False
        for raw_clause in raw_filters:
            if not isinstance(raw_clause, Mapping):
                filters.append(raw_clause)
                continue

            clause = dict(raw_clause)
            if (
                str(clause.get("field") or "").strip().casefold() == "status"
                and str(clause.get("op") or "").strip().casefold() == "eq"
            ):
                value = clause.get("value")
                if isinstance(value, bool):
                    raise ValueError("AUTOTASK_TICKET_STATUS_VALUE_INVALID")
                if isinstance(value, int):
                    filters.append(clause)
                    continue

                text = str(value or "").strip()
                if not text:
                    raise ValueError("AUTOTASK_TICKET_STATUS_VALUE_INVALID")
                try:
                    clause["value"] = int(text)
                except ValueError:
                    clause["value"] = self._resolve_ticket_status_label(
                        prepared=prepared,
                        label=text,
                    )
                changed = True

            filters.append(clause)

        if not changed:
            return prepared

        normalized_search = dict(search)
        normalized_search["filter"] = filters
        params = dict(prepared.params)
        params["search"] = json.dumps(
            normalized_search,
            separators=(",", ":"),
            sort_keys=True,
        )
        return PreparedRequest(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
            audit_operation=prepared.audit_operation,
        )

    def _resolve_impersonation_resource_id(
        self,
        *,
        prepared: PreparedRequest,
        email: str,
    ) -> int:
        search = json.dumps(
            {
                "MaxRecords": 2,
                "filter": [
                    {
                        "op": "eq",
                        "field": "email",
                        "value": email,
                    }
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/Resources/query",
            headers=prepared.headers,
            params={"search": search},
            timeout_seconds=prepared.timeout_seconds,
        )
        raw_items = payload.get("items") if isinstance(payload, Mapping) else None
        if not isinstance(raw_items, list):
            raise PermissionError("AUTOTASK_REQUESTER_RESOURCE_LOOKUP_INVALID")

        matches: list[int] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            candidate_email = str(item.get("email") or "").strip().casefold()
            if candidate_email != email:
                continue
            active = item.get("isActive")
            if active is False or active == 0:
                continue
            try:
                resource_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            if resource_id > 0:
                matches.append(resource_id)

        if len(set(matches)) != 1:
            raise PermissionError("AUTOTASK_REQUESTER_RESOURCE_NOT_UNIQUE")
        return matches[0]

    _ATTACHMENT_READ_OPERATIONS = frozenset({
        "autotask.ticket.attachments.list",
        "autotask.ticket.attachment.get",
        "autotask.ticket.attachment.content.get",
    })

    def _verify_attachment_ticket_company(self, request: ConnectorRequest) -> None:
        if request.context.capability not in self._ATTACHMENT_READ_OPERATIONS:
            return
        try:
            expected_company = int(request.arguments.get("company_id"))
            ticket_id = int(request.arguments.get("ticket_id"))
        except (TypeError, ValueError) as exc:
            raise PermissionError("AUTOTASK_ATTACHMENT_SCOPE_INVALID") from exc
        if expected_company < 1 or ticket_id < 1:
            raise PermissionError("AUTOTASK_ATTACHMENT_SCOPE_INVALID")
        ticket_request = ConnectorRequest(
            context=replace(request.context, capability="autotask.ticket.get"),
            arguments={"ticket_id": ticket_id},
        )
        observed = AutotaskConnector.execute(self, ticket_request).data
        items = observed.get("items") if isinstance(observed, Mapping) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_NOT_UNIQUE")
        try:
            observed_ticket = int(items[0].get("id"))
            observed_company = int(items[0].get("companyID"))
        except (TypeError, ValueError) as exc:
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_SCOPE_INVALID") from exc
        if observed_ticket != ticket_id or observed_company != expected_company:
            raise PermissionError("AUTOTASK_ATTACHMENT_TICKET_COMPANY_MISMATCH")

    @staticmethod
    def _sanitize_attachment_metadata(payload: Any) -> Any:
        if isinstance(payload, Mapping):
            return {
                str(key): AutotaskImpersonatingConnector._sanitize_attachment_metadata(value)
                for key, value in payload.items()
                if str(key) != "data"
            }
        if isinstance(payload, list):
            return [AutotaskImpersonatingConnector._sanitize_attachment_metadata(value) for value in payload]
        return payload

    def execute(self, request: ConnectorRequest):
        if request.context.capability not in self._ATTACHMENT_READ_OPERATIONS:
            return super().execute(request)
        self._verify_attachment_ticket_company(request)
        result = super().execute(request)
        if request.context.capability != "autotask.ticket.attachment.content.get":
            return type(result)(
                capability=result.capability, provider=result.provider,
                data=self._sanitize_attachment_metadata(result.data),
                evidence_ids=result.evidence_ids, warnings=result.warnings,
            )
        data = result.data
        raw = data.get("data") if isinstance(data, Mapping) else None
        if raw is None and isinstance(data, Mapping) and isinstance(data.get("item"), Mapping):
            raw = data["item"].get("data")
        if raw is None and isinstance(data, Mapping):
            items = data.get("items")
            if isinstance(items, list):
                exact = [item for item in items if isinstance(item, Mapping)]
                if len(exact) != 1:
                    raise ValueError("AUTOTASK_ATTACHMENT_CONTENT_NOT_UNIQUE")
                raw = exact[0].get("data")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("AUTOTASK_ATTACHMENT_CONTENT_MISSING")
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("AUTOTASK_ATTACHMENT_CONTENT_INVALID_BASE64") from exc
        max_bytes = int(request.arguments.get("max_bytes", 6_000_000))
        if len(decoded) > max_bytes:
            raise ValueError("AUTOTASK_ATTACHMENT_CONTENT_EXCEEDS_BOUND")
        return result

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        mode = autotask_requester_authorization_mode()

        if request.context.capability == "autotask.ticket.get":
            prepared = self._prepare_ticket_read_as_query(
                request=request,
                credentials=credentials,
            )
        else:
            prepared = super().prepare_request(request, credentials)

        if request.context.capability in {
            "autotask.ticket.search",
            "autotask.ticket.count",
        }:
            prepared = self._resolve_ticket_search_status(prepared=prepared)

        if mode == AUTOTASK_AUTH_MODE_JASON_MANAGED:
            return prepared

        if request.context.capability not in _IMPERSONATED_READ_OPERATIONS:
            return prepared

        email = self._trusted_email(request)
        if email is None:
            raise PermissionError("AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED")

        resource_id = self._resolve_impersonation_resource_id(
            prepared=prepared,
            email=email,
        )
        headers = dict(prepared.headers)
        headers["ImpersonationResourceId"] = str(resource_id)
        return PreparedRequest(
            method=prepared.method,
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
            audit_operation=prepared.audit_operation,
        )


def autotask_operation_is_requester_impersonated(operation: str) -> bool:
    return (
        autotask_requester_authorization_mode() == AUTOTASK_AUTH_MODE_IMPERSONATED
        and str(operation).strip() in _IMPERSONATED_READ_OPERATIONS
    )
