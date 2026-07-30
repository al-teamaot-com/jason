from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorAuthorizationError, ConnectorRequest, ConnectorResult, HttpTransport, SecretResolver, require_capability


class N8nConnector:
    provider_name = "n8n"
    capabilities = frozenset({"n8n.workflow.invoke", "n8n.workflow.status", "n8n.execution.get"})

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        approved_workflows: Mapping[str, str],
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._approved_workflows = dict(approved_workflows)

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve("n8n.runtime", request.context)
        base_url = credentials["base_url"].rstrip("/")
        headers = {"X-N8N-API-KEY": credentials["api_key"], "Accept": "application/json"}
        capability = request.context.capability

        if capability == "n8n.workflow.invoke":
            logical_name = str(request.arguments.get("workflow", ""))
            workflow_id = self._approved_workflows.get(logical_name)
            if not workflow_id:
                raise ConnectorAuthorizationError("Workflow is not approved for Jason invocation.")
            method, path, body = "POST", f"/api/v1/workflows/{workflow_id}/run", {"data": dict(request.arguments.get("input", {}))}
        elif capability == "n8n.workflow.status":
            logical_name = str(request.arguments.get("workflow", ""))
            workflow_id = self._approved_workflows.get(logical_name)
            if not workflow_id:
                raise ConnectorAuthorizationError("Workflow is not approved for Jason inspection.")
            method, path, body = "GET", f"/api/v1/workflows/{workflow_id}", None
        elif capability == "n8n.execution.get":
            method, path, body = "GET", f"/api/v1/executions/{int(request.arguments['execution_id'])}", None
        else:
            raise ConnectorAuthorizationError("Unsupported n8n capability.")

        self._audit.record("connector.requested", request.context, {"provider": self.provider_name, "operation": path})
        payload = self._transport.request(method=method, url=f"{base_url}{path}", headers=headers, json=body)
        self._audit.record("connector.completed", request.context, {"provider": self.provider_name})
        return ConnectorResult(capability, self.provider_name, payload)
