from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorRequest,
    ConnectorResult,
    SecretResolver,
    require_capability,
)
from connectors.kfs.client import KfsApiClient


class KfsConnector:
    provider_name = "kfs"
    logical_secret = "kfs.runtime"
    capabilities = frozenset(
        {
            "kfs.group.list",
            "kfs.device.list",
            "kfs.device.get",
            "kfs.device_log.list",
            "kfs.device_log.get",
        }
    )

    def __init__(
        self,
        secrets: SecretResolver,
        audit: AuditSink,
        *,
        base_url: str,
        api_version: int = 6,
        client_factory=KfsApiClient,
    ) -> None:
        self._secrets = secrets
        self._audit = audit
        self._base_url = base_url
        self._api_version = api_version
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )
        path, body = self._resolve_operation(
            request.context.capability,
            request.arguments,
            credentials,
        )
        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": path},
        )
        payload = self._client_factory(
            credentials,
            base_url=self._base_url,
            api_version=self._api_version,
        ).call(path, body)
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )

    @staticmethod
    def _common(
        credentials: Mapping[str, str],
        bodid: str,
    ) -> dict[str, Any]:
        return {
            "RequestFrom": credentials["request_from"],
            "RequestTo": credentials["request_to"],
            "BODID": bodid,
        }

    @classmethod
    def _resolve_operation(
        cls,
        capability: str,
        arguments: Mapping[str, Any],
        credentials: Mapping[str, str],
    ) -> tuple[str, Mapping[str, Any]]:
        if capability == "kfs.group.list":
            body = cls._common(
                credentials,
                "Global_KFS_Pull_GroupList",
            )
            body["groupAttrIds"] = list(
                arguments.get("group_attr_ids") or ["all"]
            )
            return "/KFS/GroupList", body

        if capability == "kfs.device.list":
            group_id = str(arguments.get("group_id", "")).strip()
            if not group_id:
                raise ValueError("group_id is required")
            body = cls._common(
                credentials,
                "Global_KFS_Pull_DeviceList",
            )
            body.update(
                {
                    "groupId": group_id,
                    "scope": int(arguments.get("scope", 3)),
                    "deviceAttrIds": list(
                        arguments.get("device_attr_ids") or ["all"]
                    ),
                    "counters": list(
                        arguments.get("counters") or ["all"]
                    ),
                }
            )
            if arguments.get("acquisition_date") is not None:
                body["acquisitionDate"] = int(
                    arguments["acquisition_date"]
                )
            return "/KFS/DeviceList", body

        if capability == "kfs.device.get":
            device_id = str(
                arguments.get("device_id")
                or arguments.get("resource_id")
                or ""
            ).strip()
            if not device_id:
                raise ValueError("device_id or resource_id is required")
            body = cls._common(
                credentials,
                "Global_KFS_Pull_Device",
            )
            body.update(
                {
                    "device": device_id,
                    "deviceAttrIds": list(
                        arguments.get("device_attr_ids") or ["all"]
                    ),
                    "counters": list(
                        arguments.get("counters") or ["all"]
                    ),
                }
            )
            if arguments.get("acquisition_date") is not None:
                body["acquisitionDate"] = int(
                    arguments["acquisition_date"]
                )
            return "/KFS/Device", body

        if capability == "kfs.device_log.list":
            group_id = str(arguments.get("group_id", "")).strip()
            if not group_id:
                raise ValueError("group_id is required")
            body = cls._common(
                credentials,
                "Global_KFS_Pull_DeviceLogList",
            )
            body.update(
                {
                    "groupId": group_id,
                    "detail": arguments.get(
                        "detail",
                        "string-errorcode_all",
                    ),
                }
            )
            if arguments.get("from_acquisition_date") is not None:
                body["fromAcquisitionDate"] = int(
                    arguments["from_acquisition_date"]
                )
            if arguments.get("group_tree_state") is not None:
                body["groupTreeState"] = int(
                    arguments["group_tree_state"]
                )
            return "/KFS/DeviceLogList", body

        if capability == "kfs.device_log.get":
            device_id = str(
                arguments.get("device_id")
                or arguments.get("resource_id")
                or ""
            ).strip()
            if not device_id:
                raise ValueError("device_id or resource_id is required")
            body = cls._common(
                credentials,
                "Global_KFS_Pull_DeviceLog",
            )
            body.update(
                {
                    "device": device_id,
                    "detail": arguments.get(
                        "detail",
                        "string-errorcode_all",
                    ),
                }
            )
            if arguments.get("from_acquisition_date") is not None:
                body["fromAcquisitionDate"] = int(
                    arguments["from_acquisition_date"]
                )
            return "/KFS/DeviceLog", body

        raise ValueError(f"Unsupported capability: {capability}")
