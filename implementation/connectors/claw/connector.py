from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorRequest,
    ConnectorResult,
    SecretResolver,
)

from .client import ClawMcpClient

CLAW_BRIDGE_READ = "claw.capabilities.read"
CLAW_STATUS_READ = "claw.status.read"
CLAW_ARTIFACT_READ = "claw.artifact.read"
CLAW_TASK_REQUEST_SEARCH = "claw.task_request.search"
CLAW_TASK_REQUEST_CREATE = "claw.task_request.create"

CLAW_READ_CAPABILITIES = frozenset(
    {
        CLAW_BRIDGE_READ,
        CLAW_STATUS_READ,
        CLAW_ARTIFACT_READ,
        CLAW_TASK_REQUEST_SEARCH,
    }
)
CLAW_WRITE_CAPABILITIES = frozenset({CLAW_TASK_REQUEST_CREATE})

ALLOWED_ARTIFACTS = frozenset(
    {
        "automation_health",
        "daily_ops_json",
        "daily_ops_latest",
        "gpt_insight_trace",
        "heartbeat",
        "kfs_dashboard",
        "ops_snapshot",
        "saas_alerts_log",
        "saas_alerts_usage",
        "status_board",
        "today_memory",
        "todo",
        "worklog",
    }
)


class ClawConnector:
    provider_name = "claw"
    logical_secret = "claw.runtime"
    capabilities = CLAW_READ_CAPABILITIES | CLAW_WRITE_CAPABILITIES

    def __init__(
        self,
        secrets: SecretResolver,
        audit: AuditSink,
        *,
        client_factory=ClawMcpClient,
    ) -> None:
        self._secrets = secrets
        self._audit = audit
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        capability = request.context.capability
        if capability not in self.capabilities:
            raise ConnectorAuthorizationError(
                f"Capability is not registered for Claw: {capability}"
            )
        if capability in CLAW_READ_CAPABILITIES and request.context.mode != "observe":
            raise ConnectorAuthorizationError("Claw read capability requires observe mode.")
        if capability in CLAW_WRITE_CAPABILITIES and request.context.mode != "execute":
            raise ConnectorAuthorizationError("Claw task creation requires execute mode.")

        credentials = self._secrets.resolve(self.logical_secret, request.context)
        tool, arguments = self._resolve_operation(
            capability,
            request.arguments,
            request.context.correlation_id,
        )
        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": tool},
        )
        payload = self._client_factory(credentials).call_tool(tool, arguments)
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name, "operation": tool},
        )
        return ConnectorResult(
            capability=capability,
            provider=self.provider_name,
            data=payload,
        )

    @staticmethod
    def _resolve_operation(
        capability: str,
        arguments: Mapping[str, Any],
        correlation_id: str,
    ) -> tuple[str, Mapping[str, Any]]:
        if capability == CLAW_BRIDGE_READ:
            return "openclaw_bridge_status", {}
        if capability == CLAW_STATUS_READ:
            return "openclaw_status_summary", {}
        if capability == CLAW_ARTIFACT_READ:
            key = str(arguments.get("key") or "").strip()
            if key not in ALLOWED_ARTIFACTS:
                raise ValueError("Claw artifact key is not allowlisted.")
            max_bytes = int(arguments.get("max_bytes") or arguments.get("maxBytes") or 40000)
            if not 0 < max_bytes <= 200000:
                raise ValueError("Claw artifact max_bytes must be between 1 and 200000.")
            return "openclaw_read_artifact", {"key": key, "maxBytes": max_bytes}
        if capability == CLAW_TASK_REQUEST_SEARCH:
            limit = int(arguments.get("limit") or 20)
            if not 0 < limit <= 100:
                raise ValueError("Claw task request limit must be between 1 and 100.")
            return "openclaw_list_task_requests", {"limit": limit}
        if capability == CLAW_TASK_REQUEST_CREATE:
            title = str(arguments.get("title") or "").strip()
            body = str(arguments.get("body") or "").strip()
            priority = str(arguments.get("priority") or "normal").strip().casefold()
            if not 3 <= len(title) <= 180:
                raise ValueError("Claw task title must be between 3 and 180 characters.")
            if not 1 <= len(body) <= 8000:
                raise ValueError("Claw task body must be between 1 and 8000 characters.")
            if priority not in {"low", "normal", "high", "urgent"}:
                raise ValueError("Claw task priority is invalid.")
            return (
                "openclaw_create_task_request",
                {
                    "title": title,
                    "body": body,
                    "priority": priority,
                    "requestedBy": "Jason",
                    "correlationId": correlation_id,
                },
            )
        raise ValueError(f"Unsupported Claw capability: {capability}")
