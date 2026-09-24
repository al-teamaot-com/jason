from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository

from .connector import DNSFILTER_PROFILE, DNSFILTER_PROVIDER
from .mcp_client import DnsFilterMcpClient
from .mcp_oauth import DnsFilterMcpOAuthStore

DNSFILTER_MCP_PROVIDER = "dnsfilter_mcp"

_CAPABILITY_TO_TOOL = {
    "dnsfilter_mcp.query_logs.search": "search_query_logs",
    "dnsfilter_mcp.query_decision.explain": "explain_query_decision",
    "dnsfilter_mcp.blocked_traffic.search": "get_blocked_traffic",
    "dnsfilter_mcp.traffic_anomalies.search": "detect_traffic_anomalies",
    "dnsfilter_mcp.stale_agents.search": "stale_agents",
    "dnsfilter_mcp.agent_version.report": "agent_version_report",
    "dnsfilter_mcp.duplicate_agents.search": "duplicate_agents",
    "dnsfilter_mcp.site_policy_drift.search": "sites_not_using_policy",
    "dnsfilter_mcp.policy_category.search": "policies_with_category",
    "dnsfilter_mcp.unblock_requests.search": "list_unblock_requests",
    "dnsfilter_mcp.unblock_requests.count": "pending_unblock_requests_count",
}

_ALLOWED_ARGUMENTS = {
    "search_query_logs": {
        "company_id","from","to","fqdn","domain","agent_id","agent_ids",
        "network_id","network_ids","user_id","user_ids","result","source",
        "question_type","private_ip","security_report","category_ids",
        "application_ids","page","per_page","compact",
    },
    "explain_query_decision": {
        "company_id","fqdn","from","to","agent_id","network_id",
    },
    "get_blocked_traffic": {
        "company_id","from","to","limit",
    },
    "detect_traffic_anomalies": {
        "company_id","from","to","network_id",
    },
    "stale_agents": {"company_id","days"},
    "agent_version_report": {"company_id","latest_version"},
    "duplicate_agents": {"company_id"},
    "sites_not_using_policy": {"company_id","policy_id"},
    "policies_with_category": {
        "company_id","category_id","include_global_policies",
    },
    "list_unblock_requests": {
        "company_id","tab","page","per_page","requested_after",
        "requested_before","resolved_after","resolved_before","search",
        "sort","status",
    },
    "pending_unblock_requests_count": {"company_id"},
}


class DnsFilterMcpConnector:
    provider_name = DNSFILTER_MCP_PROVIDER
    capabilities = frozenset(_CAPABILITY_TO_TOOL)

    def __init__(
        self,
        *,
        oauth_store: DnsFilterMcpOAuthStore,
        audit: AuditSink,
        boundaries: ClientBoundaryRepository,
        client_factory=DnsFilterMcpClient,
    ) -> None:
        self._oauth_store = oauth_store
        self._audit = audit
        self._boundaries = boundaries
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot":
            raise ConnectorAuthorizationError(
                "DNSFilter MCP reads are restricted to the AOT organization."
            )
        tool_name = _CAPABILITY_TO_TOOL[request.context.capability]
        arguments = dict(request.arguments)
        self._validate_arguments(tool_name, arguments)
        company_id, organization_id = self._resolve_boundary(
            request.context,
            arguments,
        )
        provider_arguments = {
            key: value
            for key, value in arguments.items()
            if key != "company_id"
        }
        provider_arguments["organization_id"] = organization_id

        self._audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "tool": tool_name,
                "company_id": company_id,
                "organization_boundary_validated": True,
                "oauth_user_session": True,
            },
        )
        client = self._client_factory(self._oauth_store)
        data = client.call_tool(tool_name, provider_arguments)
        self._assert_response_scope(
            data,
            organization_id,
            tool_name=tool_name,
        )
        self._audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "tool": tool_name,
                "company_id": company_id,
                "organization_boundary_validated": True,
            },
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _validate_arguments(
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> None:
        forbidden = {
            "organization_id","organization_ids","msp_id","confirm",
        }.intersection(arguments)
        if forbidden:
            raise ConnectorAuthorizationError(
                "DNSFilter MCP organization scope and confirmations are server-derived."
            )
        unexpected = sorted(
            set(arguments) - _ALLOWED_ARGUMENTS[tool_name]
        )
        if unexpected:
            raise ConnectorConfigurationError(
                "DNSFilter MCP request contains unsupported argument(s): "
                + ", ".join(unexpected)
            )
        if tool_name == "search_query_logs":
            if not arguments.get("from") or not arguments.get("to"):
                raise ConnectorConfigurationError(
                    "DNS query-log search requires from and to."
                )
        if tool_name in {
            "get_blocked_traffic",
            "detect_traffic_anomalies",
        }:
            if not arguments.get("from") or not arguments.get("to"):
                raise ConnectorConfigurationError(
                    f"DNSFilter MCP {tool_name} requires from and to."
                )
        if tool_name == "explain_query_decision" and not str(
            arguments.get("fqdn") or ""
        ).strip():
            raise ConnectorConfigurationError(
                "DNS query decision explanation requires fqdn."
            )
        for key in ("page","per_page","limit","days"):
            if key not in arguments:
                continue
            try:
                value = int(arguments[key])
            except (TypeError, ValueError) as exc:
                raise ConnectorConfigurationError(
                    f"DNSFilter MCP {key} must be an integer."
                ) from exc
            if value < 1:
                raise ConnectorConfigurationError(
                    f"DNSFilter MCP {key} must be positive."
                )
            if key == "per_page" and value > 100:
                raise ConnectorConfigurationError(
                    "DNSFilter MCP per_page must be 1-100."
                )
            if key == "limit" and value > 100:
                raise ConnectorConfigurationError(
                    "DNSFilter MCP limit must be 1-100."
                )

    def _resolve_boundary(
        self,
        context: ConnectorContext,
        arguments: Mapping[str, Any],
    ) -> tuple[str, int]:
        raw_company_id = arguments.get("company_id")
        if isinstance(raw_company_id, bool):
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter MCP access."
            )
        try:
            company_id = str(int(raw_company_id))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter MCP access."
            ) from exc
        if int(company_id) < 0:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter MCP access."
            )
        if (
            context.client_id is not None
            and str(context.client_id) != company_id
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter MCP request client scope does not match the selected company."
            )
        boundary = self._boundaries.find_active_for_client(
            client_id=company_id,
            provider=DNSFILTER_PROVIDER,
        )
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ConnectorAuthorizationError(
                "No validated DNSFilter organization boundary exists for this company."
            )
        if boundary.profile != DNSFILTER_PROFILE:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary uses an unapproved profile."
            )
        try:
            organization_id = int(str(boundary.external_tenant_id))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary contains an invalid organization ID."
            ) from exc
        if organization_id < 1:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary contains an invalid organization ID."
            )
        return company_id, organization_id

    @staticmethod
    def _assert_response_scope(
        data: Mapping[str, Any],
        expected_organization_id: int,
        *,
        tool_name: str,
    ) -> None:
        # DNSFilter's MCP tools are invoked with an injected organization_id.
        # When the returned payload repeats the organization identifier, verify
        # it exactly. Some aggregate tools omit it; for those the provider-side
        # scoped request remains the enforceable boundary.
        candidates = []
        for key in ("organization_id","organizationId"):
            if key in data:
                candidates.append(data[key])
        organization = data.get("organization")
        if isinstance(organization, Mapping):
            for key in ("id","organization_id"):
                if key in organization:
                    candidates.append(organization[key])
        for observed in candidates:
            try:
                value = int(str(observed))
            except (TypeError, ValueError) as exc:
                raise ConnectorAuthorizationError(
                    "DNSFilter MCP response contained an invalid organization identifier."
                ) from exc
            if value != expected_organization_id:
                raise ConnectorAuthorizationError(
                    "DNSFilter MCP response crossed the authorized organization boundary."
                )
