from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorRequest

from .connector import AutotaskConnector


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


# Restrict requester impersonation to canonical provider operations whose Autotask
# entities are documented as supporting impersonation/query security. Expanding this
# set requires provider documentation plus focused tests.
_IMPERSONATED_READ_OPERATIONS = frozenset(
    {
        "autotask.company.get",
        "autotask.company.search",
        "autotask.ticket.get",
        "autotask.ticket.search",
    }
)


@dataclass(frozen=True, slots=True)
class AutotaskImpersonationEvidence:
    applied: bool
    basis: str | None = None


class AutotaskImpersonatingConnector(AutotaskConnector):
    """Execute selected Autotask reads as the authenticated Jason requester.

    Autotask REST authentication still uses the dedicated API-only integration
    account. For supported read entities, the connector resolves the already-
    authenticated Jason principal through the durable Microsoft binding, maps that
    trusted email to exactly one Autotask Resource, and supplies Autotask's
    `ImpersonationResourceId` header on the provider read.

    The mapping lookup is internal evidence used only to establish the provider
    enforcement identity. Missing or ambiguous trusted bindings, and zero or multiple
    matching Autotask resources, fail closed before the requested provider read is
    sent. Caller-provided arguments can never choose the impersonated resource.
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
        prepared = super().prepare_request(request, credentials)

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
    return str(operation).strip() in _IMPERSONATED_READ_OPERATIONS
