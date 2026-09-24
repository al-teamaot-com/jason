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
        "user_id","user_ids","result","source","question_type","private_ip",
        "security_report","category_ids","application_ids","page","per_page","compact",
    },
    "explain_query_decision": {
        "company_id","fqdn","from","to","agent_id",
    },
    "get_blocked_traffic": {"company_id","from","to","limit"},
    "detect_traffic_anomalies": {"company_id","from","to"},
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

_FORBIDDEN_SCOPE_ARGUMENTS = frozenset(
    {"organization_id","organization_ids","msp_id","network_id","network_ids","site_id","site_ids","confirm"}
)
_MULTI_NETWORK_TOOLS = frozenset({"search_query_logs"})
_SINGLE_NETWORK_TOOLS = frozenset({"explain_query_decision", "detect_traffic_anomalies"})
_ORGANIZATION_ONLY_TOOLS = frozenset(_CAPABILITY_TO_TOOL.values()) - _MULTI_NETWORK_TOOLS - _SINGLE_NETWORK_TOOLS


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
        company_id, organization_id, network_ids = self._resolve_boundary(
            request.context, arguments
        )
        client_scoped = company_id != "0"

        if client_scoped and tool_name in _ORGANIZATION_ONLY_TOOLS:
            raise ConnectorAuthorizationError(
                f"DNSFilter MCP tool {tool_name} cannot prove client-network isolation."
            )
        if client_scoped and tool_name in _SINGLE_NETWORK_TOOLS and len(network_ids) != 1:
            raise ConnectorAuthorizationError(
                f"DNSFilter MCP tool {tool_name} requires exactly one authorized client network."
            )

        provider_arguments = {
            key: value for key, value in arguments.items() if key != "company_id"
        }
        provider_arguments["organization_id"] = organization_id
        if client_scoped and tool_name in _MULTI_NETWORK_TOOLS:
            provider_arguments["network_ids"] = list(network_ids)
        elif client_scoped and tool_name in _SINGLE_NETWORK_TOOLS:
            provider_arguments["network_id"] = network_ids[0]

        audit_scope = {
            "provider": self.provider_name,
            "tool": tool_name,
            "company_id": company_id,
            "organization_id": organization_id,
            "network_scope_ids": list(network_ids),
            "organization_boundary_validated": True,
            "network_boundary_validated": bool(network_ids) or not client_scoped,
            "oauth_user_session": True,
        }
        self._audit.record("connector.requested", request.context, audit_scope)
        client = self._client_factory(self._oauth_store)
        data = client.call_tool(tool_name, provider_arguments)
        verification = self._assert_response_scope(
            data,
            organization_id,
            network_ids,
            tool_name=tool_name,
            client_scoped=client_scoped,
        )
        self._audit.record(
            "connector.completed",
            request.context,
            {**audit_scope, "scope_verification": verification},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _validate_arguments(tool_name: str, arguments: Mapping[str, Any]) -> None:
        if _FORBIDDEN_SCOPE_ARGUMENTS.intersection(arguments):
            raise ConnectorAuthorizationError(
                "DNSFilter MCP organization and network scope is server-derived."
            )
        unexpected = sorted(set(arguments) - _ALLOWED_ARGUMENTS[tool_name])
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
        if tool_name in {"get_blocked_traffic", "detect_traffic_anomalies"}:
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
            if key in {"per_page", "limit"} and value > 100:
                raise ConnectorConfigurationError(
                    f"DNSFilter MCP {key} must be 1-100."
                )

    def _resolve_boundary(
        self,
        context: ConnectorContext,
        arguments: Mapping[str, Any],
    ) -> tuple[str, int, tuple[int, ...]]:
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
        if context.client_id is not None and str(context.client_id) != company_id:
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

        scopes: list[int] = []
        for raw_scope in boundary.external_scope_ids:
            try:
                scope_id = int(str(raw_scope))
            except (TypeError, ValueError) as exc:
                raise ConnectorAuthorizationError(
                    "DNSFilter client boundary contains an invalid network ID."
                ) from exc
            if scope_id < 1:
                raise ConnectorAuthorizationError(
                    "DNSFilter client boundary contains an invalid network ID."
                )
            scopes.append(scope_id)
        network_ids = tuple(sorted(set(scopes)))
        if company_id != "0" and not network_ids:
            raise ConnectorAuthorizationError(
                "No validated DNSFilter network boundary exists for this company."
            )
        return company_id, organization_id, network_ids

    @classmethod
    def _assert_response_scope(
        cls,
        data: Mapping[str, Any],
        expected_organization_id: int,
        network_ids: tuple[int, ...],
        *,
        tool_name: str,
        client_scoped: bool,
    ) -> str:
        organization_candidates: list[Any] = []
        for key in ("organization_id","organizationId"):
            if key in data:
                organization_candidates.append(data[key])
        organization = data.get("organization")
        if isinstance(organization, Mapping):
            for key in ("id","organization_id"):
                if key in organization:
                    organization_candidates.append(organization[key])
        for observed in organization_candidates:
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

        if not client_scoped:
            return "organization_scope"

        observed_networks = cls._collect_network_ids(data)
        if observed_networks and not observed_networks.issubset(frozenset(network_ids)):
            raise ConnectorAuthorizationError(
                "DNSFilter MCP response crossed the authorized client network boundary."
            )
        if tool_name in _MULTI_NETWORK_TOOLS | _SINGLE_NETWORK_TOOLS:
            return (
                "network_response_verified"
                if observed_networks
                else "provider_request_network_scope"
            )
        return "organization_scope"

    @classmethod
    def _collect_network_ids(cls, value: Any) -> set[int]:
        observed: set[int] = set()
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"network_id", "networkId"} and child not in (None, ""):
                    try:
                        observed.add(int(str(child)))
                    except (TypeError, ValueError) as exc:
                        raise ConnectorAuthorizationError(
                            "DNSFilter MCP response contained an invalid network identifier."
                        ) from exc
                else:
                    observed.update(cls._collect_network_ids(child))
        elif isinstance(value, list):
            for child in value:
                observed.update(cls._collect_network_ids(child))
        return observed
