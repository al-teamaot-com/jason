from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)

from .client import DarkWebIdClient, require_darkwebid_credentials

DARKWEBID_PROVIDER = "darkwebid"
DARKWEBID_SECRET = "darkwebid.runtime"

_CAPABILITY_OPERATIONS = {
    "darkwebid.organization.search": "organization_search",
    "darkwebid.organization.read": "organization_read",
}


class DarkWebIdConnector:
    provider_name = DARKWEBID_PROVIDER
    logical_secret = DARKWEBID_SECRET
    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        *,
        client_factory=DarkWebIdClient,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot" or request.context.client_id is not None:
            raise ConnectorAuthorizationError(
                "Dark Web ID organization inventory is currently authorized only for AOT-internal organization-wide reads."
            )

        operation = _CAPABILITY_OPERATIONS[request.context.capability]
        arguments = dict(request.arguments)
        self._validate_arguments(operation, arguments)
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        require_darkwebid_credentials(credentials)
        client = self._client_factory(credentials)

        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        data = self._execute_operation(client, operation, arguments)
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _validate_arguments(operation: str, arguments: Mapping[str, Any]) -> None:
        if operation == "organization_search":
            allowed = {"page", "limit"}
            unexpected = sorted(set(arguments) - allowed)
            if unexpected:
                raise ConnectorConfigurationError(
                    "Dark Web ID organization search contains unsupported argument(s): "
                    + ", ".join(unexpected)
                )
            try:
                page = int(arguments.get("page", 0))
                limit = int(arguments.get("limit", 200))
            except (TypeError, ValueError) as exc:
                raise ConnectorConfigurationError(
                    "Dark Web ID page and limit must be integers."
                ) from exc
            if page < 0:
                raise ConnectorConfigurationError(
                    "Dark Web ID page must be zero or greater."
                )
            if not 1 <= limit <= 200:
                raise ConnectorConfigurationError(
                    "Dark Web ID limit must be between 1 and 200."
                )
            return

        if operation == "organization_read":
            if set(arguments) != {"uuid"}:
                raise ConnectorConfigurationError(
                    "Dark Web ID organization read requires exactly uuid."
                )
            uuid = str(arguments.get("uuid") or "").strip()
            if not uuid or "/" in uuid or ".." in uuid:
                raise ConnectorConfigurationError(
                    "Dark Web ID organization uuid is invalid."
                )
            return

        raise ConnectorConfigurationError("Unsupported Dark Web ID operation.")

    @staticmethod
    def _execute_operation(
        client: DarkWebIdClient,
        operation: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if operation == "organization_search":
            return client.get(
                "services/organization.json",
                {
                    "page": int(arguments.get("page", 0)),
                    "limit": int(arguments.get("limit", 200)),
                },
            )
        if operation == "organization_read":
            uuid = str(arguments["uuid"]).strip()
            return client.get(f"services/organization/{uuid}.json")
        raise ConnectorConfigurationError("Unsupported Dark Web ID operation.")
