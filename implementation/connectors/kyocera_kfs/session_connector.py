from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)
from connectors.kyocera_kfs.client import (
    KyoceraKfsSessionClient,
    require_kfs_credentials,
)
from connectors.kyocera_kfs.read_operations import (
    SUPPLY_ATTRIBUTES,
    alerts_list,
    device_get,
    device_search,
    require_device_id,
)

_CAPABILITY_OPERATIONS = {
    "kyocera_kfs.device.search": "device_search",
    "kyocera_kfs.device.get": "device_get",
    "kyocera_kfs.meters.get": "meters_get",
    "kyocera_kfs.supplies.get": "supplies_get",
    "kyocera_kfs.alerts.list": "alerts_list",
}


class KyoceraKfsSessionConnector:
    provider_name = "kyocera_kfs"
    logical_secret = "kyocera_kfs.readonly"
    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        *,
        client_factory=KyoceraKfsSessionClient,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot" or request.context.client_id is not None:
            raise ConnectorAuthorizationError(
                "Kyocera KFS is currently authorized only for AOT-internal organization-wide reads."
            )
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        require_kfs_credentials(credentials)
        operation = _CAPABILITY_OPERATIONS[request.context.capability]

        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        client = self._client_factory(credentials)
        data = self._execute_operation(client, operation, request.arguments)
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _execute_operation(
        client: KyoceraKfsSessionClient,
        operation: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if operation == "device_search":
            return device_search(client, arguments)

        device_id = None
        if operation in {"device_get", "meters_get", "supplies_get"}:
            device_id = require_device_id(arguments)

        if operation == "device_get":
            return device_get(client, device_id, ("all",), ("all",))
        if operation == "meters_get":
            return device_get(
                client,
                device_id,
                ("manufacturer", "modelName", "serialNumber", "managementStatus"),
                ("all",),
            )
        if operation == "supplies_get":
            return device_get(client, device_id, SUPPLY_ATTRIBUTES, ("total",))
        if operation == "alerts_list":
            return alerts_list(client, arguments)
        raise ValueError(f"Unsupported Kyocera KFS operation: {operation}")
