from __future__ import annotations

from typing import Any, Mapping

from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorRequest,
    ConnectorResult,
)

from .connector import AutotaskConnector
from .impersonating_connector import (
    AUTOTASK_AUTH_MODE_IMPERSONATED,
    AutotaskImpersonatingConnector,
    autotask_requester_authorization_mode,
)


AUTOTASK_MUTATION_OPERATIONS = frozenset(
    {
        "autotask.ticket.create",
        "autotask.ticket.update",
        "autotask.ticket.note.create",
        "autotask.ticket.note.update",
    }
)

_OPERATION_PREFLIGHT = {
    "autotask.ticket.create": ("Tickets", "userAccessForCreate"),
    "autotask.ticket.update": ("Tickets", "userAccessForUpdate"),
    "autotask.ticket.note.create": ("TicketNotes", "userAccessForCreate"),
    "autotask.ticket.note.update": ("TicketNotes", "userAccessForUpdate"),
}


class AutotaskMutationConnector(AutotaskImpersonatingConnector):
    """Dormant, provider-enforced Autotask Ticket/TicketNote mutation path.

    The ordinary :class:`AutotaskConnector` and the global connector foundation
    remain read-only. This connector adds only four explicitly approved mutation
    primitives and will refuse every mutation unless provider-native requester
    impersonation is active.

    The authenticated Jason principal is resolved through the trusted binding
    inherited from ``AutotaskImpersonatingConnector`` and must map to exactly one
    active Autotask Resource. The provider's entityInformation user-access field
    is then queried under that same ``ImpersonationResourceId``. Access ``None``
    fails before mutation; ``All`` or ``Restricted`` permit the concrete provider
    request to become the final record-level enforcement point.
    """

    capabilities = AutotaskConnector.capabilities | AUTOTASK_MUTATION_OPERATIONS

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        """Execute only an explicitly registered mutation in ``execute`` mode.

        Read requests continue through the inherited read-only connector path.
        This intentionally avoids weakening ``connectors.core.require_capability``
        for every other provider connector in Jason.
        """

        if request.context.capability not in AUTOTASK_MUTATION_OPERATIONS:
            return super().execute(request)

        if request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "Autotask mutation requires explicit execute mode."
            )

        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )
        prepared = self.prepare_request(request, credentials)
        operation = prepared.audit_operation or prepared.url

        self._audit.record(
            "connector.mutation.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": operation,
            },
        )

        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )

        self._audit.record(
            "connector.mutation.completed",
            request.context,
            {
                "provider": self.provider_name,
                "operation": operation,
            },
        )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )

    @staticmethod
    def _user_access_value(payload: Mapping[str, Any], field: str) -> int:
        raw = payload.get(field)
        if raw is None:
            item = payload.get("item")
            if isinstance(item, Mapping):
                raw = item.get(field)

        if isinstance(raw, bool):
            raise PermissionError("AUTOTASK_MUTATION_PREFLIGHT_INVALID")

        try:
            value = int(raw)
        except (TypeError, ValueError) as error:
            raise PermissionError(
                "AUTOTASK_MUTATION_PREFLIGHT_INVALID"
            ) from error

        if value not in {0, 1, 2}:
            raise PermissionError("AUTOTASK_MUTATION_PREFLIGHT_INVALID")
        return value

    def _preflight_requester_access(
        self,
        *,
        prepared: PreparedRequest,
        headers: Mapping[str, str],
        operation: str,
    ) -> None:
        entity, access_field = _OPERATION_PREFLIGHT[operation]
        payload = self._transport.request(
            method="GET",
            url=f"{self._api_root(prepared)}/V1.0/{entity}/entityInformation",
            headers=headers,
            params=None,
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        if not isinstance(payload, Mapping):
            raise PermissionError("AUTOTASK_MUTATION_PREFLIGHT_INVALID")

        if self._user_access_value(payload, access_field) == 0:
            raise PermissionError("AUTOTASK_REQUESTER_OPERATION_NOT_PERMITTED")

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        operation = request.context.capability
        if operation not in AUTOTASK_MUTATION_OPERATIONS:
            return super().prepare_request(request, credentials)

        # Mutations never use Jason-managed/service-account authority. Fail
        # before zone discovery or any other provider I/O if impersonation is
        # not explicitly active.
        if autotask_requester_authorization_mode() != AUTOTASK_AUTH_MODE_IMPERSONATED:
            raise PermissionError("AUTOTASK_WRITE_REQUIRES_REQUESTER_IMPERSONATION")

        # Compile the bounded request using the base connector. Do not call the
        # parent impersonating prepare_request here because its supported
        # impersonation set intentionally contains read operations only.
        prepared = AutotaskConnector.prepare_request(self, request, credentials)

        email = self._trusted_email(request)
        if email is None:
            raise PermissionError("AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED")

        resource_id = self._resolve_impersonation_resource_id(
            prepared=prepared,
            email=email,
        )
        headers = dict(prepared.headers)
        headers["ImpersonationResourceId"] = str(resource_id)

        self._preflight_requester_access(
            prepared=prepared,
            headers=headers,
            operation=operation,
        )

        return PreparedRequest(
            method=prepared.method,
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
            audit_operation=prepared.audit_operation,
        )
