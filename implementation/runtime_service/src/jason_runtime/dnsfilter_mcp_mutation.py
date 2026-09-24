from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import re
from typing import Any, Mapping, Sequence

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRequest,
    ConnectorResult,
    ConnectorTransportError,
)
from connectors.dnsfilter.mcp_connector import DnsFilterMcpConnector
from connectors.dnsfilter.mcp_oauth import DnsFilterMcpOAuthStore
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.connector_invoker import (
    GovernedConnectorCapabilityInvoker,
    ProviderPreparedExecution,
)
from orchestrator.dnsfilter_mcp_mutation_capability_catalog import (
    DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES,
    DNSFILTER_MCP_MUTATION_TOOLS,
    dnsfilter_mcp_mutation_capabilities,
)
from orchestrator.invokers import CapabilityInvokerRegistry

DNSFILTER_MCP_MUTATION_ENABLED_ENV = "JASON_DNSFILTER_MCP_MUTATION_ENABLED"
DNSFILTER_MCP_MUTATION_PROFILE_ENV = "JASON_DNSFILTER_MCP_MUTATION_PROFILE"
DNSFILTER_MCP_MUTATION_PROFILE = "governed_v1"
DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_PROFILE = (
    "policy_create_acceptance_v1"
)
DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_CAPABILITY = (
    "dns.protection.policy.create"
)
DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE = (
    "policy_delete_acceptance_v1"
)
DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_CAPABILITY = (
    "dns.protection.policy.delete"
)
DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_POLICY_ID = "1506474"
DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_POLICY_NAME = (
    "Jason DNSFilter Governed Write Test 2026-09-24"
)
DNSFILTER_MCP_MUTATION_PROVIDER = "dnsfilter_mcp_mutation"


class DnsFilterMutationVerificationError(RuntimeError):
    pass


class DnsFilterMutationUnknownOutcomeError(RuntimeError):
    pass
_CANONICAL_BY_PROVIDER = {
    provider_capability: canonical
    for canonical, provider_capability
    in DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.items()
}
_TOOL_BY_PROVIDER = {
    provider_capability: DNSFILTER_MCP_MUTATION_TOOLS[canonical]
    for provider_capability, canonical in _CANONICAL_BY_PROVIDER.items()
}

_REQUIRED = {
    "add_blocklist_domain": {"policy_id", "domain"},
    "add_allowlist_domain": {"policy_id", "domain"},
    "remove_blocklist_domain": {"policy_id", "domain"},
    "remove_allowlist_domain": {"policy_id", "domain"},
    "add_blocklist_category": {"policy_id", "category_id"},
    "remove_blocklist_category": {"policy_id", "category_id"},
    "bulk_add_blocklist_domains": {"domains", "policy_ids"},
    "bulk_add_allowlist_domains": {"domains", "policy_ids"},
    "add_global_list_domain": {"domain", "list_type"},
    "remove_global_list_domain": {"domain", "list_type"},
    "set_category_across_org_policies": {"category_id", "action"},
    "clone_policy": {"source_policy_id"},
    "create_policy": {"name"},
    "update_policy": {"policy_id"},
    "delete_policy": {"policy_id"},
    "apply_policy_to_sites": {"policy_id", "network_ids"},
    "invite_user": {"email", "role"},
    "change_user_role": {"user_id", "role"},
    "send_password_reset": {"email"},
    "reassign_agent_policy": {"user_agent_id", "policy_id"},
    "uninstall_agent": {"user_agent_id"},
    "bulk_remove_agents": {"user_agent_ids"},
    "update_site_forwarders": {"network_id", "local_resolvers"},
    "update_block_page": {"block_page_id"},
    "decide_unblock_request": {"request_id", "decision"},
}

_ALLOWED = {
    "add_blocklist_domain": {"company_id", "policy_id", "domain"},
    "add_allowlist_domain": {"company_id", "policy_id", "domain"},
    "remove_blocklist_domain": {"company_id", "policy_id", "domain"},
    "remove_allowlist_domain": {"company_id", "policy_id", "domain"},
    "add_blocklist_category": {"company_id", "policy_id", "category_id"},
    "remove_blocklist_category": {"company_id", "policy_id", "category_id"},
    "bulk_add_blocklist_domains": {"company_id", "domains", "policy_ids"},
    "bulk_add_allowlist_domains": {"company_id", "domains", "policy_ids"},
    "add_global_list_domain": {"company_id", "domain", "list_type"},
    "remove_global_list_domain": {"company_id", "domain", "list_type"},
    "set_category_across_org_policies": {"company_id", "category_id", "action"},
    "clone_policy": {"company_id", "source_policy_id", "new_name"},
    "create_policy": {
        "company_id", "name", "allow_list_only", "allow_unknown_domains",
        "allowed_domains", "bing_safe_search", "blocked_application_names",
        "blocked_category_ids", "blocked_domains", "duck_duck_go_safe_search",
        "google_safesearch", "policy_ip_id", "youtube_restricted_level",
    },
    "update_policy": {
        "company_id", "policy_id", "allow_list_only", "allow_unknown_domains",
        "bing_safe_search", "duck_duck_go_safe_search", "google_safesearch",
        "interstitial", "name", "policy_ip_id", "youtube_restricted_level",
    },
    "delete_policy": {"company_id", "policy_id", "force"},
    "apply_policy_to_sites": {"company_id", "policy_id", "network_ids"},
    "invite_user": {"company_id", "email", "role", "first_name", "last_name"},
    "change_user_role": {"company_id", "user_id", "role"},
    "send_password_reset": {"company_id", "email"},
    "reassign_agent_policy": {"company_id", "user_agent_id", "policy_id"},
    "uninstall_agent": {"company_id", "user_agent_id"},
    "bulk_remove_agents": {"company_id", "user_agent_ids"},
    "update_site_forwarders": {
        "company_id", "network_id", "local_resolvers", "local_domains",
    },
    "update_block_page": {
        "company_id", "block_page_id", "block_email_addr", "block_logo_uuid",
        "block_org_name", "block_redirect_url", "name",
    },
    "decide_unblock_request": {
        "company_id", "request_id", "decision", "internal_notes", "message",
    },
}

_ORG_INJECT = {
    "add_global_list_domain": "organization_id",
    "remove_global_list_domain": "organization_id",
    "set_category_across_org_policies": "organization_id",
    "clone_policy": "target_organization_id",
    "create_policy": "organization_id",
    "invite_user": "organization_id",
    "change_user_role": "organization_id",
    "send_password_reset": "organization_id",
    "bulk_remove_agents": "organization_id",
}

# Child Autotask companies can share the AOT DNSFilter organization. Only
# mutations whose complete blast radius can be proven from the child's exact
# network boundary are eligible at child scope. All other administrative
# mutations are master-scope only (Autotask company 0).
_CLIENT_SCOPED_MUTATION_TOOLS = frozenset(
    {
        "apply_policy_to_sites",
        "reassign_agent_policy",
        "uninstall_agent",
        "bulk_remove_agents",
        "update_site_forwarders",
    }
)

_ENUMS = {
    "list_type": {"allow", "block"},
    "action": {"block", "unblock"},
    "role": {
        "administrator", "super_administrator", "read_only",
        "technical", "accountant", "policies_only",
    },
    "youtube_restricted_level": {"none", "moderate", "strict"},
    "decision": {
        "allow", "allow-universal", "deny", "deny-and-ignore",
        "resolve-already-allowed",
    },
}

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)


@dataclass(frozen=True, slots=True)
class _PreparedDnsFilterMutation:
    request: ConnectorRequest
    tool_name: str
    company_id: str
    organization_id: int
    network_scope_ids: tuple[int, ...]
    client_scoped: bool
    provider_arguments: Mapping[str, Any]
    resource_type: str
    resource_identifier: str
    preflight: Mapping[str, Any]


def dnsfilter_mcp_mutation_execution_enabled() -> bool:
    raw = os.getenv(DNSFILTER_MCP_MUTATION_ENABLED_ENV)
    if raw is None:
        return False
    value = raw.strip().casefold()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError("DNSFILTER_MCP_MUTATION_ENABLEMENT_INVALID")
@dataclass(frozen=True, slots=True)
class DnsFilterMcpMutationActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


class DnsFilterMcpMutationActivationError(RuntimeError):
    pass


def _mutation_capabilities_for_profile(profile: str) -> tuple[str, ...]:
    if profile == DNSFILTER_MCP_MUTATION_PROFILE:
        return tuple(sorted(DNSFILTER_MCP_MUTATION_TOOLS))
    if profile == DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_PROFILE:
        return (DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_CAPABILITY,)
    if profile == DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE:
        return (DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_CAPABILITY,)
    raise DnsFilterMcpMutationActivationError(
        "unsupported DNSFilter MCP mutation profile"
    )


def dnsfilter_mcp_mutation_surface_enabled() -> bool:
    profile = os.getenv(
        DNSFILTER_MCP_MUTATION_PROFILE_ENV, ""
    ).strip().casefold()
    if not profile:
        return False
    try:
        _mutation_capabilities_for_profile(profile)
    except DnsFilterMcpMutationActivationError:
        return False
    return dnsfilter_mcp_mutation_execution_enabled()


def _dnsfilter_mcp_mutation_provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DNSFILTER_MCP_MUTATION_PROVIDER,
        display_name="DNSFilter MCP Governed Administration",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.BLOCKED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(DNSFILTER_MCP_MUTATION_TOOLS),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=90,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Permit explicitly approved DNSFilter administrative actions "
                "through the provider-supported OAuth MCP surface."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "DNSFilter removes or materially changes the mapped MCP tools.",
                "A safer provider-supported administrative surface replaces MCP.",
            ),
            vendor_change_sources=(
                "DNSFilter MCP connector documentation",
                "DNSFilter MCP public tool catalog",
            ),
            operational_owner="AOT Managed Services",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "dnsfilter_mcp",
            "resource_authority": "dns_protection",
            "write_capability": "true",
            "provider_confirmation_required": "true",
            "activation_state": "source_present_not_activated",
        },
    )


def register_dnsfilter_mcp_mutation_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> DnsFilterMcpMutationActivationState:
    definitions = dnsfilter_mcp_mutation_capabilities(now)
    for definition in definitions:
        capabilities.register(definition)
    providers.register(_dnsfilter_mcp_mutation_provider(now=now))

    profile = os.getenv(
        DNSFILTER_MCP_MUTATION_PROFILE_ENV, ""
    ).strip().casefold()
    execution_enabled = dnsfilter_mcp_mutation_execution_enabled()
    if not execution_enabled:
        return DnsFilterMcpMutationActivationState(
            profile=profile,
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )
    if not profile:
        raise DnsFilterMcpMutationActivationError(
            "DNSFilter MCP mutation execution gate requires an activation profile"
        )
    capability_names = _mutation_capabilities_for_profile(profile)

    for capability_name in capability_names:
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=DNSFILTER_MCP_MUTATION_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=DNSFILTER_MCP_MUTATION_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=DNSFILTER_MCP_MUTATION_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return DnsFilterMcpMutationActivationState(
        profile=profile,
        enabled=True,
        provider_ids=(DNSFILTER_MCP_MUTATION_PROVIDER,),
        capability_names=capability_names,
    )


def build_dnsfilter_mcp_mutation_invoker(
    *,
    oauth_store: DnsFilterMcpOAuthStore,
    audit: Any,
    boundaries: Any,
) -> GovernedConnectorCapabilityInvoker:
    connector = DnsFilterMcpGovernedConnector(
        oauth_store=oauth_store,
        audit=audit,
        boundaries=boundaries,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={DNSFILTER_MCP_MUTATION_PROVIDER: connector},
        provider_capability_map={
            (
                DNSFILTER_MCP_MUTATION_PROVIDER,
                canonical,
            ): provider_capability
            for canonical, provider_capability
            in DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.items()
        },
    )


def register_dnsfilter_mcp_mutation_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: GovernedConnectorCapabilityInvoker,
    capability_names: Sequence[str],
) -> None:
    unknown = sorted(set(capability_names) - set(DNSFILTER_MCP_MUTATION_TOOLS))
    if unknown:
        raise DnsFilterMcpMutationActivationError(
            "cannot register unknown DNSFilter mutation capabilities: "
            + ", ".join(unknown)
        )
    for capability_name in sorted(set(capability_names)):
        invokers.register(capability_name, invoker)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ConnectorConfigurationError(f"{name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConnectorConfigurationError(
            f"{name} must be a positive integer."
        ) from exc
    if parsed < 1:
        raise ConnectorConfigurationError(f"{name} must be a positive integer.")
    return parsed


def _identifier(value: Any, name: str) -> int | str:
    if isinstance(value, bool) or value is None:
        raise ConnectorConfigurationError(f"{name} is invalid.")
    if isinstance(value, int):
        return _positive_int(value, name)
    text = str(value).strip()
    if not text:
        raise ConnectorConfigurationError(f"{name} is invalid.")
    if text.isdigit():
        return _positive_int(text, name)
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,31}", text
    ):
        raise ConnectorConfigurationError(f"{name} is invalid.")
    return text.lower()


def _bounded_text(value: Any, name: str, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise ConnectorConfigurationError(
            f"{name} must contain 1-{limit} characters."
        )
    return text
def _domain(value: Any, name: str = "domain") -> str:
    text = _bounded_text(value, name, limit=253).lower().rstrip(".")
    if not _DOMAIN_RE.fullmatch(text):
        raise ConnectorConfigurationError(f"{name} must be a DNS hostname.")
    return text


def _bounded_list(
    value: Any,
    name: str,
    *,
    maximum: int,
) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConnectorConfigurationError(f"{name} must be an array.")
    result = list(value)
    if not result or len(result) > maximum:
        raise ConnectorConfigurationError(
            f"{name} must contain 1-{maximum} items."
        )
    return result


def _resource(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, Mapping) else payload


def _attributes(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    attrs = _resource(payload).get("attributes")
    return attrs if isinstance(attrs, Mapping) else {}


def _relationship_id(payload: Mapping[str, Any], name: str) -> str | None:
    rels = _resource(payload).get("relationships")
    if not isinstance(rels, Mapping):
        return None
    rel = rels.get(name)
    data = rel.get("data") if isinstance(rel, Mapping) else None
    if isinstance(data, Mapping) and data.get("id") is not None:
        return str(data["id"])
    return None
def _organization_id(payload: Mapping[str, Any]) -> int | None:
    candidates = [
        payload.get("organization_id"),
        _resource(payload).get("organization_id"),
        _attributes(payload).get("organization_id"),
        _relationship_id(payload, "organization"),
    ]
    for value in candidates:
        if value is None:
            continue
        try:
            return int(str(value))
        except (TypeError, ValueError):
            continue
    return None


def _contains_id(value: Any, expected: int | str) -> bool:
    needle = str(expected)
    if isinstance(value, Mapping):
        if value.get("id") is not None and str(value["id"]) == needle:
            return True
        return any(_contains_id(item, expected) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_id(item, expected) for item in value)
    return str(value) == needle


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    result = set()
    for item in value:
        if isinstance(item, Mapping):
            candidate = item.get("domain") or item.get("name") or item.get("value")
        else:
            candidate = item
        if candidate is not None:
            result.add(str(candidate).strip().lower().rstrip("."))
    return result
class DnsFilterMcpGovernedConnector(DnsFilterMcpConnector):
    """Governed DNSFilter MCP mutation adapter.

    Reads remain on the existing dnsfilter_mcp connector. This adapter exposes
    mutation provider capabilities only, and direct execute() is never allowed;
    every write must travel through the execution-plan path.
    """

    provider_name = DNSFILTER_MCP_MUTATION_PROVIDER
    mutation_capabilities = frozenset(_TOOL_BY_PROVIDER)
    capabilities = mutation_capabilities

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        raise ConnectorAuthorizationError(
            "DNSFilter mutations require the governed execution-plan path."
        )

    def prepare_governed_execution(
        self,
        request: ConnectorRequest,
    ) -> ProviderPreparedExecution:
        if request.context.capability not in self.mutation_capabilities:
            raise ConnectorAuthorizationError(
                "DNSFilter governed mutation capability is not registered."
            )
        if request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "DNSFilter mutation requires explicit execute mode."
            )
        if not dnsfilter_mcp_mutation_execution_enabled():
            raise PermissionError("DNSFILTER_MCP_MUTATION_EXECUTION_DISABLED")

        tool_name = _TOOL_BY_PROVIDER[request.context.capability]
        active_profile = os.getenv(
            DNSFILTER_MCP_MUTATION_PROFILE_ENV, ""
        ).strip().casefold()
        if (
            active_profile == DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_PROFILE
            and tool_name != "create_policy"
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter policy-create acceptance profile permits only create_policy."
            )
        if (
            active_profile == DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE
            and tool_name != "delete_policy"
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter policy-delete acceptance profile permits only delete_policy."
            )
        raw = dict(request.arguments)
        normalized = self._normalize_arguments(tool_name, raw)
        company_id, organization_id, network_scope_ids = self._resolve_boundary(
            request.context, {"company_id": raw.get("company_id")}
        )
        client_scoped = company_id != "0"
        if client_scoped and tool_name not in _CLIENT_SCOPED_MUTATION_TOOLS:
            raise ConnectorAuthorizationError(
                f"DNSFilter mutation {tool_name} is master-scope only because "
                "its complete blast radius cannot be proven from a client network boundary."
            )
        provider_arguments = {
            key: value for key, value in normalized.items()
            if key != "company_id"
        }
        injected = _ORG_INJECT.get(tool_name)
        if injected:
            provider_arguments[injected] = organization_id

        client = self._client_factory(self._oauth_store)
        preflight = self._preflight(
            client,
            tool_name,
            provider_arguments,
            organization_id,
            network_scope_ids=network_scope_ids,
            client_scoped=client_scoped,
        )
        provider_arguments["confirm"] = True
        resource_type, resource_identifier = self._target(
            tool_name, provider_arguments, organization_id
        )
        prepared_request = ConnectorRequest(
            context=request.context,
            arguments={"company_id": int(company_id), **provider_arguments},
        )
        self._audit.record(
            "connector.mutation.prepared",
            request.context,
            {
                "provider": self.provider_name,
                "tool": tool_name,
                "company_id": company_id,
                "organization_boundary_validated": True,
                "confirm_server_injected": True,
            },
        )
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method="MCP_TOOL_CALL",
            resource_type=resource_type,
            resource_identifier=resource_identifier,
            normalized_path=f"/tools/{tool_name}",
            payload=dict(provider_arguments),
            parameters={},
            symbolic_resolutions={
                "company_id": company_id,
                "organization_id": organization_id,
                "network_scope_ids": list(network_scope_ids),
                "client_scoped": client_scoped,
                **dict(preflight),
            },
            opaque=_PreparedDnsFilterMutation(
                request=prepared_request,
                tool_name=tool_name,
                company_id=company_id,
                organization_id=organization_id,
                network_scope_ids=network_scope_ids,
                client_scoped=client_scoped,
                provider_arguments=dict(provider_arguments),
                resource_type=resource_type,
                resource_identifier=resource_identifier,
                preflight=dict(preflight),
            ),
        )

    def execute_governed_execution(
        self,
        prepared_execution: ProviderPreparedExecution,
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedDnsFilterMutation):
            raise PermissionError("Invalid DNSFilter prepared mutation.")
        if not dnsfilter_mcp_mutation_execution_enabled():
            raise PermissionError("DNSFILTER_MCP_MUTATION_EXECUTION_DISABLED")
        if prepared_execution.provider_capability != opaque.request.context.capability:
            raise PermissionError("DNSFilter provider capability binding changed.")
        if prepared_execution.action_method != "MCP_TOOL_CALL":
            raise PermissionError("DNSFilter mutation method binding changed.")
        if prepared_execution.normalized_path != f"/tools/{opaque.tool_name}":
            raise PermissionError("DNSFilter mutation tool binding changed.")
        if prepared_execution.resource_type != opaque.resource_type:
            raise PermissionError("DNSFilter mutation resource type changed.")
        if prepared_execution.resource_identifier != opaque.resource_identifier:
            raise PermissionError("DNSFilter mutation target changed.")
        if dict(prepared_execution.payload) != dict(opaque.provider_arguments):
            raise PermissionError("DNSFilter mutation payload binding changed.")
        if dict(prepared_execution.parameters):
            raise PermissionError("DNSFilter mutation parameters must be empty.")
        if opaque.provider_arguments.get("confirm") is not True:
            raise PermissionError("DNSFilter provider confirmation is not bound.")

        self._audit.record(
            "connector.mutation.requested",
            opaque.request.context,
            {
                "provider": self.provider_name,
                "tool": opaque.tool_name,
                "company_id": opaque.company_id,
                "organization_id": opaque.organization_id,
            },
        )
        client = self._client_factory(self._oauth_store)
        try:
            result = client.call_tool(
                opaque.tool_name, opaque.provider_arguments
            )
        except ConnectorTransportError as exc:
            readback_recovery_allowed = (
                (
                    opaque.tool_name == "create_policy"
                    and opaque.preflight.get(
                        "policy_name_unique_before_write"
                    ) is True
                )
                or (
                    opaque.tool_name == "delete_policy"
                    and opaque.preflight.get(
                        "policy_delete_acceptance_target_verified"
                    ) is True
                )
            )
            if readback_recovery_allowed:
                try:
                    verification = self._verify(
                        client,
                        opaque.tool_name,
                        opaque.provider_arguments,
                        opaque.organization_id,
                        {},
                        network_scope_ids=opaque.network_scope_ids,
                        client_scoped=opaque.client_scoped,
                    )
                except Exception:
                    verification = None
                if verification is not None:
                    recovered = {
                        **dict(verification),
                        "providerErrorRecoveredByReadback": True,
                    }
                    self._audit.record(
                        "connector.mutation.recovered_by_readback",
                        opaque.request.context,
                        {
                            "provider": self.provider_name,
                            "tool": opaque.tool_name,
                            "company_id": opaque.company_id,
                            "organization_id": opaque.organization_id,
                        },
                    )
                    return ConnectorResult(
                        capability=opaque.request.context.capability,
                        provider=self.provider_name,
                        data={
                            "providerOutcome": "error_recovered_by_readback",
                            "jasonVerification": recovered,
                        },
                        evidence_ids=(
                            f"dnsfilter:organization:{opaque.organization_id}",
                            f"dnsfilter:tool:{opaque.tool_name}",
                        ),
                    )

            self._audit.record(
                "connector.mutation.unknown_outcome",
                opaque.request.context,
                {
                    "provider": self.provider_name,
                    "tool": opaque.tool_name,
                    "readback_matched": False,
                },
            )
            raise DnsFilterMutationUnknownOutcomeError(
                "DNSFilter mutation outcome is unknown; no automatic retry is permitted."
            ) from exc

        verification = self._verify(
            client,
            opaque.tool_name,
            opaque.provider_arguments,
            opaque.organization_id,
            result,
            network_scope_ids=opaque.network_scope_ids,
            client_scoped=opaque.client_scoped,
        )
        self._audit.record(
            "connector.mutation.verified",
            opaque.request.context,
            {
                "provider": self.provider_name,
                "tool": opaque.tool_name,
                "company_id": opaque.company_id,
                "organization_id": opaque.organization_id,
            },
        )
        data = dict(result)
        data["jasonVerification"] = verification
        return ConnectorResult(
            capability=opaque.request.context.capability,
            provider=self.provider_name,
            data=data,
            evidence_ids=(
                f"dnsfilter:organization:{opaque.organization_id}",
                f"dnsfilter:tool:{opaque.tool_name}",
            ),
        )

    def _normalize_arguments(
        self,
        tool_name: str,
        raw: Mapping[str, Any],
    ) -> dict[str, Any]:
        forbidden = {
            "organization_id", "target_organization_id", "organization_ids",
            "msp_id", "confirm",
        }.intersection(raw)
        if forbidden:
            raise ConnectorAuthorizationError(
                "DNSFilter scope and provider confirmation are server-derived."
            )
        allowed = _ALLOWED[tool_name]
        unexpected = sorted(set(raw) - allowed)
        if unexpected:
            raise ConnectorConfigurationError(
                "Unsupported DNSFilter mutation argument(s): "
                + ", ".join(unexpected)
            )
        missing = sorted(
            key for key in _REQUIRED[tool_name]
            if raw.get(key) is None or raw.get(key) == ""
        )
        if missing:
            raise ConnectorConfigurationError(
                "Missing DNSFilter mutation argument(s): " + ", ".join(missing)
            )
        if raw.get("company_id") is None:
            raise ConnectorConfigurationError(
                "An exact Autotask company_id is required."
            )

        out = dict(raw)
        for key in ("policy_id", "source_policy_id"):
            if key in out:
                out[key] = _identifier(out[key], key)
        for key in (
            "category_id", "network_id", "block_page_id", "user_id",
            "policy_ip_id",
        ):
            if key in out:
                out[key] = _positive_int(out[key], key)
        for key in ("network_ids", "policy_ids"):
            if key in out:
                out[key] = [
                    _positive_int(item, key)
                    for item in _bounded_list(out[key], key, maximum=50)
                ]
        if "user_agent_ids" in out:
            out["user_agent_ids"] = [
                _bounded_text(item, "user_agent_id", limit=80)
                for item in _bounded_list(
                    out["user_agent_ids"], "user_agent_ids", maximum=50
                )
            ]
        if "domains" in out:
            out["domains"] = [
                _domain(item)
                for item in _bounded_list(out["domains"], "domains", maximum=100)
            ]
        for key in ("domain",):
            if key in out:
                out[key] = _domain(out[key], key)
        for key in ("allowed_domains", "blocked_domains", "local_domains"):
            if key in out:
                out[key] = [
                    _domain(item, key)
                    for item in _bounded_list(out[key], key, maximum=100)
                ]
        for key in ("blocked_category_ids",):
            if key in out:
                out[key] = [
                    _positive_int(item, key)
                    for item in _bounded_list(out[key], key, maximum=100)
                ]
        for key in ("blocked_application_names", "local_resolvers"):
            if key in out:
                out[key] = [
                    _bounded_text(item, key, limit=255)
                    for item in _bounded_list(out[key], key, maximum=100)
                ]
        for key, choices in _ENUMS.items():
            if key in out:
                value = str(out[key]).strip().casefold()
                if value not in choices:
                    raise ConnectorConfigurationError(
                        f"{key} must be one of: {', '.join(sorted(choices))}."
                    )
                out[key] = value
        for key in ("email",):
            if key in out:
                value = _bounded_text(out[key], key, limit=320).lower()
                if "@" not in value:
                    raise ConnectorConfigurationError("email is invalid.")
                out[key] = value
        for key in (
            "name", "new_name", "first_name", "last_name",
            "block_email_addr", "block_logo_uuid", "block_org_name",
            "block_redirect_url", "internal_notes", "message",
        ):
            if key in out and out[key] not in (None, ""):
                out[key] = _bounded_text(out[key], key, limit=2000)
        for key in ("user_agent_id", "request_id"):
            if key in out:
                out[key] = _bounded_text(out[key], key, limit=128)
        return out

    def _preflight(
        self,
        client: Any,
        tool: str,
        args: Mapping[str, Any],
        organization_id: int,
        *,
        network_scope_ids: tuple[int, ...],
        client_scoped: bool,
    ) -> Mapping[str, Any]:
        resolved: dict[str, Any] = {}
        policy_ids: list[int | str] = []
        policy_payloads: dict[str, Mapping[str, Any]] = {}
        for key in ("policy_id", "source_policy_id"):
            if key in args:
                policy_ids.append(args[key])
        policy_ids.extend(args.get("policy_ids") or [])
        for policy_id in policy_ids:
            payload = client.call_tool(
                "get_policy",
                {"policy_id": policy_id, "include_relationships": True},
            )
            self._require_scope(payload, organization_id, "policy")
            policy_payloads[str(policy_id)] = payload
        if policy_ids:
            resolved["policy_ids"] = [str(item) for item in policy_ids]
        network_ids = []
        if "network_id" in args:
            network_ids.append(args["network_id"])
        network_ids.extend(args.get("network_ids") or [])
        authorized_networks = frozenset(network_scope_ids)
        if client_scoped and any(
            int(network_id) not in authorized_networks
            for network_id in network_ids
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter mutation target crossed the authorized client network boundary."
            )
        for network_id in network_ids:
            payload = client.call_tool(
                "get_network",
                {"network_id": network_id, "count_network_ips": False},
            )
            self._require_scope(payload, organization_id, "network")
        if network_ids:
            resolved["network_ids"] = [str(item) for item in network_ids]

        if tool == "create_policy":
            requested_name = str(args["name"])
            exact_matches = [
                policy
                for policy in self._policy_pages(client, organization_id)
                if str(
                    (policy.get("attributes") or {}).get("name") or ""
                ) == requested_name
            ]
            if exact_matches:
                raise ConnectorConfigurationError(
                    "DNSFilter policy with the exact requested name already exists."
                )
            resolved["policy_name_unique_before_write"] = True

        active_profile = os.getenv(
            DNSFILTER_MCP_MUTATION_PROFILE_ENV, ""
        ).strip().casefold()
        if (
            tool == "delete_policy"
            and active_profile
            == DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE
        ):
            target = str(args["policy_id"])
            if target != DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_POLICY_ID:
                raise ConnectorAuthorizationError(
                    "DNSFilter policy-delete acceptance profile permits only the "
                    "approved test policy ID."
                )
            payload = policy_payloads.get(target)
            resource = _resource(payload or {})
            attrs = resource.get("attributes")
            if not isinstance(attrs, Mapping):
                raise ConnectorAuthorizationError(
                    "DNSFilter policy-delete acceptance preflight did not return "
                    "policy attributes."
                )
            if (
                str(attrs.get("name") or "")
                != DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_POLICY_NAME
            ):
                raise ConnectorAuthorizationError(
                    "DNSFilter policy-delete acceptance target name did not match "
                    "the approved test policy."
                )
            if bool(attrs.get("is_global_policy")):
                raise ConnectorAuthorizationError(
                    "DNSFilter policy-delete acceptance target must not be global."
                )
            relationships = resource.get("relationships")
            if not isinstance(relationships, Mapping):
                raise ConnectorAuthorizationError(
                    "DNSFilter policy-delete acceptance preflight did not return "
                    "relationships."
                )
            assignment_keys = (
                "networks",
                "mac_addresses",
                "scheduled_policies",
                "network_subnets",
                "user_agents",
                "agent_local_users",
                "collections",
            )
            for key in assignment_keys:
                relationship = relationships.get(key)
                if not isinstance(relationship, Mapping):
                    raise ConnectorAuthorizationError(
                        "DNSFilter policy-delete acceptance could not prove "
                        f"relationship {key} is empty."
                    )
                data = relationship.get("data")
                if not isinstance(data, list):
                    raise ConnectorAuthorizationError(
                        "DNSFilter policy-delete acceptance could not prove "
                        f"relationship {key} is empty."
                    )
                if data:
                    raise ConnectorAuthorizationError(
                        "DNSFilter policy-delete acceptance target is assigned "
                        f"through relationship {key}."
                    )
            resolved["policy_delete_acceptance_target_verified"] = True
            resolved["policy_delete_acceptance_policy_id"] = target
            resolved["policy_delete_acceptance_policy_name"] = (
                DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_POLICY_NAME
            )

        if "block_page_id" in args:
            payload = client.call_tool(
                "get_block_page",
                {"block_page_id": args["block_page_id"], "include_relationships": True},
            )
            self._require_scope(payload, organization_id, "block page")
            resolved["block_page_id"] = str(args["block_page_id"])

        if "request_id" in args:
            payload = client.call_tool(
                "get_unblock_request", {"request_id": args["request_id"]}
            )
            self._require_scope(payload, organization_id, "unblock request")
            resolved["request_id"] = str(args["request_id"])

        if "user_id" in args:
            user = self._find_user_by_id(
                client, organization_id, args["user_id"]
            )
            if user is None:
                raise ConnectorAuthorizationError(
                    "DNSFilter portal user does not belong to the mapped organization."
                )
            resolved["user_id"] = str(args["user_id"])
        if tool == "send_password_reset":
            user = client.call_tool(
                "user_lookup",
                {"organization_id": organization_id, "email": args["email"]},
            )
            if _organization_id(user) not in (None, organization_id):
                raise ConnectorAuthorizationError(
                    "DNSFilter password-reset target crossed organization boundary."
                )
            resolved["email"] = args["email"]

        agent_ids = []
        if "user_agent_id" in args:
            agent_ids.append(str(args["user_agent_id"]))
        agent_ids.extend(str(item) for item in args.get("user_agent_ids") or [])
        if agent_ids:
            agents = self._agent_index(
                client,
                organization_id,
                network_scope_ids=network_scope_ids if client_scoped else (),
            )
            missing = sorted(set(agent_ids) - set(agents))
            if missing:
                raise ConnectorAuthorizationError(
                    "DNSFilter agent target does not belong to the mapped organization."
                )
            resolved["user_agent_ids"] = sorted(agent_ids)
        return resolved

    @staticmethod
    def _require_scope(
        payload: Mapping[str, Any],
        expected_organization_id: int,
        label: str,
    ) -> None:
        observed = _organization_id(payload)
        if observed is None:
            raise ConnectorAuthorizationError(
                f"DNSFilter {label} preflight did not prove organization ownership."
            )
        if observed != expected_organization_id:
            raise ConnectorAuthorizationError(
                f"DNSFilter {label} crossed the authorized organization boundary."
            )

    @staticmethod
    def _target(
        tool: str,
        args: Mapping[str, Any],
        organization_id: int,
    ) -> tuple[str, str]:
        for key, resource_type in (
            ("policy_id", "dns_policy"),
            ("source_policy_id", "dns_policy"),
            ("network_id", "dns_site"),
            ("block_page_id", "dns_block_page"),
            ("user_id", "dns_portal_user"),
            ("email", "dns_portal_user"),
            ("user_agent_id", "dns_agent"),
            ("request_id", "dns_unblock_request"),
        ):
            if key in args:
                return resource_type, str(args[key])
        for key, resource_type in (
            ("policy_ids", "dns_policy_set"),
            ("network_ids", "dns_site_set"),
            ("user_agent_ids", "dns_agent_set"),
        ):
            if key in args:
                return resource_type, ",".join(str(item) for item in args[key])
        return "dns_organization", str(organization_id)

    def _policy_pages(
        self, client: Any, organization_id: int
    ) -> list[Mapping[str, Any]]:
        items: list[Mapping[str, Any]] = []
        for page in range(1, 11):
            payload = client.call_tool(
                "list_policies",
                {"organization_id": organization_id, "page": page, "per_page": 100},
            )
            data = payload.get("data")
            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, Mapping))
            pagination = payload.get("pagination")
            if not isinstance(pagination, Mapping) or not pagination.get("has_more"):
                return items
        raise DnsFilterMutationVerificationError(
            "DNSFilter policy readback exceeded the bounded 1000-policy verification limit."
        )

    def _agent_index(
        self,
        client: Any,
        organization_id: int,
        *,
        network_scope_ids: tuple[int, ...] = (),
    ) -> dict[str, Mapping[str, Any]]:
        items: dict[str, Mapping[str, Any]] = {}
        for page in range(1, 11):
            arguments: dict[str, Any] = {
                "organization_ids": [organization_id],
                "page": page,
                "per_page": 100,
            }
            if network_scope_ids:
                arguments["network_ids"] = list(network_scope_ids)
            payload = client.call_tool(
                "list_user_agents",
                arguments,
            )
            data = payload.get("data")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, Mapping) and item.get("id") is not None:
                        items[str(item["id"])] = item
            pagination = payload.get("pagination")
            if not isinstance(pagination, Mapping) or not pagination.get("has_more"):
                return items
        raise DnsFilterMutationVerificationError(
            "DNSFilter agent readback exceeded the bounded 1000-agent verification limit."
        )

    def _find_user_by_id(
        self, client: Any, organization_id: int, user_id: int
    ) -> Mapping[str, Any] | None:
        for page in range(1, 11):
            payload = client.call_tool(
                "list_users",
                {"organization_id": organization_id, "page": page, "per_page": 100},
            )
            users = payload.get("users")
            if isinstance(users, list):
                for user in users:
                    if isinstance(user, Mapping) and str(user.get("id")) == str(user_id):
                        return user
            if len(users or []) < 100:
                return None
        raise DnsFilterMutationVerificationError(
            "DNSFilter user readback exceeded the bounded 1000-user verification limit."
        )

    def _verify(
        self,
        client: Any,
        tool: str,
        args: Mapping[str, Any],
        organization_id: int,
        mutation_result: Mapping[str, Any],
        *,
        network_scope_ids: tuple[int, ...],
        client_scoped: bool,
    ) -> Mapping[str, Any]:
        if tool in {
            "add_blocklist_domain", "remove_blocklist_domain",
            "add_allowlist_domain", "remove_allowlist_domain",
            "add_blocklist_category", "remove_blocklist_category",
        }:
            payload = client.call_tool(
                "get_policy",
                {"policy_id": args["policy_id"], "include_relationships": True},
            )
            self._require_scope(payload, organization_id, "policy")
            attrs = _attributes(payload)
            if "domain" in args:
                key = (
                    "blacklist_domains"
                    if "blocklist" in tool
                    else "whitelist_domains"
                )
                present = args["domain"] in _string_set(attrs.get(key))
                expected = tool.startswith("add_")
            else:
                present = _contains_id(
                    attrs.get("blacklist_categories"), args["category_id"]
                )
                expected = tool.startswith("add_")
            if present != expected:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter policy readback did not match the approved mutation."
                )
            return {"readbackVerified": True, "tool": "get_policy"}

        if tool in {"bulk_add_blocklist_domains", "bulk_add_allowlist_domains"}:
            key = (
                "blacklist_domains"
                if tool == "bulk_add_blocklist_domains"
                else "whitelist_domains"
            )
            expected_domains = set(args["domains"])
            for policy_id in args["policy_ids"]:
                payload = client.call_tool(
                    "get_policy",
                    {"policy_id": policy_id, "include_relationships": True},
                )
                self._require_scope(payload, organization_id, "policy")
                if not expected_domains.issubset(_string_set(_attributes(payload).get(key))):
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter bulk policy-domain readback did not match."
                    )
            return {"readbackVerified": True, "tool": "get_policy"}
        if tool in {"add_global_list_domain", "remove_global_list_domain"}:
            payload = client.call_tool(
                "get_global_lists", {"organization_id": organization_id}
            )
            if _organization_id(payload) != organization_id:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter global-list readback scope mismatch."
                )
            key = (
                "whitelist_domains" if args["list_type"] == "allow"
                else "blacklist_domains"
            )
            present = args["domain"] in _string_set(payload.get(key))
            expected = tool == "add_global_list_domain"
            if present != expected:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter global-list readback did not match."
                )
            return {"readbackVerified": True, "tool": "get_global_lists"}

        if tool == "set_category_across_org_policies":
            should_block = args["action"] == "block"
            for policy in self._policy_pages(client, organization_id):
                attrs = policy.get("attributes")
                if not isinstance(attrs, Mapping):
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter policy readback shape was invalid."
                    )
                present = _contains_id(
                    attrs.get("blacklist_categories"), args["category_id"]
                )
                if present != should_block:
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter organization-wide category readback did not match."
                    )
            return {"readbackVerified": True, "tool": "list_policies"}

        if tool in {"create_policy", "clone_policy"}:
            policy_id = None
            resource = _resource(mutation_result)
            if resource.get("id") is not None:
                policy_id = resource.get("id")
            if policy_id is not None:
                payload = client.call_tool(
                    "get_policy",
                    {"policy_id": policy_id, "include_relationships": True},
                )
                self._require_scope(payload, organization_id, "policy")
                return {
                    "readbackVerified": True,
                    "tool": "get_policy",
                    "policy_id": str(policy_id),
                }

            name = args.get("name") or args.get("new_name")
            if not name:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter created policy could not be resolved for readback."
                )
            exact_matches = [
                policy
                for policy in self._policy_pages(client, organization_id)
                if str(
                    (policy.get("attributes") or {}).get("name") or ""
                ) == str(name)
            ]
            if len(exact_matches) != 1:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter created policy readback did not resolve exactly one approved name."
                )
            payload = exact_matches[0]
            self._require_scope(payload, organization_id, "policy")
            return {
                "readbackVerified": True,
                "tool": "list_policies",
                "policy_id": str(payload.get("id") or ""),
            }

        if tool == "update_policy":
            payload = client.call_tool(
                "get_policy",
                {"policy_id": args["policy_id"], "include_relationships": True},
            )
            self._require_scope(payload, organization_id, "policy")
            attrs = _attributes(payload)
            for key, expected in args.items():
                if key in {"policy_id", "confirm"}:
                    continue
                if key in attrs and attrs.get(key) != expected:
                    raise DnsFilterMutationVerificationError(
                        f"DNSFilter policy field {key} failed readback."
                    )
            return {"readbackVerified": True, "tool": "get_policy"}

        if tool == "delete_policy":
            target = str(args["policy_id"])
            if any(
                str(item.get("id")) == target
                for item in self._policy_pages(client, organization_id)
            ):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter deleted policy still appears in organization policy inventory."
                )
            return {"readbackVerified": True, "tool": "list_policies"}

        if tool == "apply_policy_to_sites":
            for network_id in args["network_ids"]:
                payload = client.call_tool(
                    "get_network",
                    {"network_id": network_id, "count_network_ips": False},
                )
                self._require_scope(payload, organization_id, "network")
                attrs = _attributes(payload)
                observed = attrs.get("policy_id") or _relationship_id(payload, "policy")
                if str(observed) != str(args["policy_id"]):
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter site policy assignment failed readback."
                    )
            return {"readbackVerified": True, "tool": "get_network"}
        if tool == "invite_user":
            payload = client.call_tool(
                "user_lookup",
                {"organization_id": organization_id, "email": args["email"]},
            )
            if _organization_id(payload) not in (None, organization_id):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter invited user readback scope mismatch."
                )
            return {"readbackVerified": True, "tool": "user_lookup"}

        if tool == "change_user_role":
            user = self._find_user_by_id(client, organization_id, args["user_id"])
            if user is None or str(user.get("role") or "").casefold() != args["role"]:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter portal-user role failed readback."
                )
            return {"readbackVerified": True, "tool": "list_users"}

        if tool == "send_password_reset":
            payload = client.call_tool(
                "user_lookup",
                {"organization_id": organization_id, "email": args["email"]},
            )
            if _organization_id(payload) not in (None, organization_id):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter password-reset identity readback scope mismatch."
                )
            return {
                "readbackVerified": True,
                "tool": "user_lookup",
                "deliveryNotProvableByReadback": True,
            }

        if tool == "reassign_agent_policy":
            agent = self._agent_index(
                client,
                organization_id,
                network_scope_ids=network_scope_ids if client_scoped else (),
            ).get(str(args["user_agent_id"]))
            if agent is None:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter agent was not found during readback."
                )
            observed = _relationship_id(agent, "policy")
            if str(observed) != str(args["policy_id"]):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter agent policy reassignment failed readback."
                )
            return {"readbackVerified": True, "tool": "list_user_agents"}
        if tool == "uninstall_agent":
            agent = self._agent_index(
                client,
                organization_id,
                network_scope_ids=network_scope_ids if client_scoped else (),
            ).get(str(args["user_agent_id"]))
            state = (
                str(_attributes(agent).get("agent_state") or "").casefold()
                if agent is not None else "removed"
            )
            if state not in {"pending_uninstall", "uninstalled", "removed"}:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter agent uninstall failed readback."
                )
            return {"readbackVerified": True, "tool": "list_user_agents"}

        if tool == "bulk_remove_agents":
            agents = self._agent_index(
                client,
                organization_id,
                network_scope_ids=network_scope_ids if client_scoped else (),
            )
            for agent_id in args["user_agent_ids"]:
                agent = agents.get(str(agent_id))
                state = (
                    str(_attributes(agent).get("agent_state") or "").casefold()
                    if agent is not None else "removed"
                )
                if state not in {"pending_uninstall", "uninstalled", "removed"}:
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter bulk agent removal failed readback."
                    )
            return {"readbackVerified": True, "tool": "list_user_agents"}

        if tool == "update_site_forwarders":
            payload = client.call_tool(
                "get_network",
                {"network_id": args["network_id"], "count_network_ips": False},
            )
            self._require_scope(payload, organization_id, "network")
            attrs = _attributes(payload)
            if sorted(attrs.get("local_resolvers") or []) != sorted(
                args["local_resolvers"]
            ):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter site forwarder readback failed."
                )
            if (
                "local_domains" in args
                and sorted(attrs.get("local_domains") or [])
                != sorted(args["local_domains"])
            ):
                raise DnsFilterMutationVerificationError(
                    "DNSFilter local-domain readback failed."
                )
            return {"readbackVerified": True, "tool": "get_network"}
        if tool == "update_block_page":
            payload = client.call_tool(
                "get_block_page",
                {
                    "block_page_id": args["block_page_id"],
                    "include_relationships": True,
                },
            )
            self._require_scope(payload, organization_id, "block page")
            attrs = _attributes(payload)
            for key, expected in args.items():
                if key in {"block_page_id", "confirm"}:
                    continue
                if attrs.get(key) != expected:
                    raise DnsFilterMutationVerificationError(
                        f"DNSFilter block-page field {key} failed readback."
                    )
            return {"readbackVerified": True, "tool": "get_block_page"}

        if tool == "decide_unblock_request":
            payload = client.call_tool(
                "get_unblock_request",
                {"request_id": args["request_id"]},
            )
            self._require_scope(payload, organization_id, "unblock request")
            resource = _resource(payload)
            attrs = resource.get("attributes")
            state = attrs if isinstance(attrs, Mapping) else resource
            observed_decision = str(
                state.get("decision") or state.get("resolution") or ""
            ).casefold()
            observed_status = str(
                state.get("status") or ""
            ).casefold()
            if observed_decision:
                if observed_decision != args["decision"]:
                    raise DnsFilterMutationVerificationError(
                        "DNSFilter unblock-request decision failed readback."
                    )
            elif observed_status in {"", "active", "pending", "open"}:
                raise DnsFilterMutationVerificationError(
                    "DNSFilter unblock request was not resolved during readback."
                )
            return {
                "readbackVerified": True,
                "tool": "get_unblock_request",
            }

        raise DnsFilterMutationVerificationError(
            f"DNSFilter mutation verifier is missing for {tool}."
        )
