from __future__ import annotations

from typing import Any, Mapping

from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorRequest,
    HttpTransport,
    SecretResolver,
)


class N8nConnector(ConnectorBase):
    provider_name = "n8n"
    logical_secret = "n8n.runtime"

    capabilities = frozenset(
        {
            "n8n.workflow.invoke",
            "n8n.workflow.status",
            "n8n.execution.get",
        }
    )

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        approved_workflows: Mapping[str, str],
    ) -> None:
        super().__init__(
            secrets=secrets,
            transport=transport,
            audit=audit,
        )
        self._approved_workflows = dict(approved_workflows)

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        method, path, body = self._resolve_operation(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method=method,
            url=f"{credentials['base_url'].rstrip('/')}{path}",
            headers={
                "X-N8N-API-KEY": credentials["api_key"],
                "Accept": "application/json",
            },
            json=body,
            audit_operation=path,
        )

    def _resolve_operation(
        self,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, str, Mapping[str, Any] | None]:
        if capability == "n8n.workflow.invoke":
            logical_name = str(
                arguments.get("workflow", "")
            )
            workflow_id = self._approved_workflows.get(
                logical_name
            )

            if not workflow_id:
                raise ConnectorAuthorizationError(
                    "Workflow is not approved for Jason invocation."
                )

            return (
                "POST",
                f"/api/v1/workflows/{workflow_id}/run",
                {
                    "data": dict(
                        arguments.get("input", {})
                    )
                },
            )

        if capability == "n8n.workflow.status":
            logical_name = str(
                arguments.get("workflow", "")
            )
            workflow_id = self._approved_workflows.get(
                logical_name
            )

            if not workflow_id:
                raise ConnectorAuthorizationError(
                    "Workflow is not approved for Jason inspection."
                )

            return (
                "GET",
                f"/api/v1/workflows/{workflow_id}",
                None,
            )

        if capability == "n8n.execution.get":
            return (
                "GET",
                "/api/v1/executions/"
                f"{int(arguments['execution_id'])}",
                None,
            )

        raise ConnectorAuthorizationError(
            "Unsupported n8n capability."
        )
