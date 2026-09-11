from __future__ import annotations

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
