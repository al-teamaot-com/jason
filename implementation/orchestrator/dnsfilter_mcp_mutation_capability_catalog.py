from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)


DNSFILTER_MCP_MUTATION_TOOLS: dict[str, str] = {
    "dns.protection.policy.domain.block.add": "add_blocklist_domain",
    "dns.protection.policy.domain.allow.add": "add_allowlist_domain",
    "dns.protection.policy.domain.block.remove": "remove_blocklist_domain",
    "dns.protection.policy.domain.allow.remove": "remove_allowlist_domain",
    "dns.protection.policy.category.block.add": "add_blocklist_category",
    "dns.protection.policy.category.block.remove": "remove_blocklist_category",
    "dns.protection.policy.domain.block.bulk.add": "bulk_add_blocklist_domains",
    "dns.protection.policy.domain.allow.bulk.add": "bulk_add_allowlist_domains",
    "dns.protection.global.list.domain.add": "add_global_list_domain",
    "dns.protection.global.list.domain.remove": "remove_global_list_domain",
    "dns.protection.policy.category.set.across.org": "set_category_across_org_policies",
    "dns.protection.policy.clone": "clone_policy",
    "dns.protection.policy.create": "create_policy",
    "dns.protection.policy.update": "update_policy",
    "dns.protection.policy.delete": "delete_policy",
    "dns.protection.site.policy.assign": "apply_policy_to_sites",
    "dns.protection.portal.user.invite": "invite_user",
    "dns.protection.portal.user.role.update": "change_user_role",
    "dns.protection.portal.user.password.reset.send": "send_password_reset",
    "dns.protection.agent.policy.reassign": "reassign_agent_policy",
    "dns.protection.agent.uninstall": "uninstall_agent",
    "dns.protection.agent.bulk.remove": "bulk_remove_agents",
    "dns.protection.site.forwarders.update": "update_site_forwarders",
    "dns.protection.block.page.update": "update_block_page",
    "dns.protection.unblock.request.decide": "decide_unblock_request",
}

_USER_DISRUPTIVE = frozenset(
    {
        "dns.protection.policy.domain.block.add",
        "dns.protection.policy.domain.allow.remove",
        "dns.protection.policy.category.block.add",
        "dns.protection.policy.domain.block.bulk.add",
        "dns.protection.global.list.domain.add",
        "dns.protection.policy.category.set.across.org",
        "dns.protection.policy.update",
        "dns.protection.policy.delete",
        "dns.protection.site.policy.assign",
        "dns.protection.agent.policy.reassign",
        "dns.protection.agent.uninstall",
        "dns.protection.agent.bulk.remove",
        "dns.protection.site.forwarders.update",
        "dns.protection.unblock.request.decide",
    }
)


def dnsfilter_mcp_mutation_capabilities(
    now: datetime,
) -> tuple[CapabilityDefinition, ...]:
    """Return dormant provider-neutral definitions for DNSFilter MCP writes.

    These definitions are source-only. They are deliberately not registered by
    runtime composition and therefore cannot be discovered or executed. Each
    provider tool independently requires confirm=true; Jason additionally
    requires explicit approval and exact target/boundary verification.
    """

    definitions: list[CapabilityDefinition] = []
    for capability_name, tool_name in DNSFILTER_MCP_MUTATION_TOOLS.items():
        definitions.append(
            CapabilityDefinition(
                capability_name=capability_name,
                version="1.0",
                display_name=capability_name.replace(".", " ").title(),
                lifecycle_status=CapabilityLifecycle.BUILDING,
                business_purpose=(
                    "Perform one explicitly approved DNSFilter administrative "
                    f"operation via provider tool {tool_name}."
                ),
                owner_service="Jason Governed DNS Protection Actions",
                architectural_capability_ids=frozenset(
                    {"JAC-005", "JAC-006", "JAC-013"}
                ),
                risk_level=CapabilityRisk.HIGH,
                data_classifications=frozenset({"internal"}),
                permitted_execution_modes=frozenset({"deterministic"}),
                input_schema_reference=(
                    f"schema://jason/{capability_name.replace('.', '-')}/1.0"
                ),
                output_schema_reference=(
                    f"schema://jason/{capability_name.replace('.', '-')}-result/1.0"
                ),
                invoking_roles=frozenset({"orchestrator"}),
                approval=CapabilityApproval(
                    required=True,
                    approver_classes=("owner", "technician"),
                ),
                evidence=CapabilityEvidence(
                    required=True,
                    requirements=(
                        "authenticated DNSFilter OAuth user",
                        "validated Autotask-company-to-DNSFilter-organization boundary",
                        "resolved provider target",
                        "bound execution plan",
                        "explicit Jason approval",
                        "provider confirm=true requirement",
                        "provider mutation result",
                        "post-write provider readback",
                    ),
                    verification_requirements=(
                        "provider tool is the exact allowlisted DNSFilter MCP tool",
                        "target belongs to the mapped organization",
                        "normalized payload matches the approved execution plan",
                        "exactly one provider mutation invocation occurs",
                        "post-write state matches the approved target state",
                    ),
                ),
                dependencies=frozenset(
                    {
                        "identity.authorization.resolve",
                        "governance.action.evaluate",
                    }
                ),
                idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
                idempotency_key_required=True,
                timeout_seconds=90,
                maximum_attempts=1,
                failure_behavior=(
                    "Fail closed without generic tool fallback, implicit retry, "
                    "cross-client selection, or unverified success."
                ),
                tenant_isolation_required=True,
                client_isolation_required=True,
                stewardship=CapabilityStewardship(
                    steward="technology-steward",
                    business_justification=(
                        "Use DNSFilter's provider-supported AI administrative "
                        "surface without bypassing Jason governance."
                    ),
                    review_interval_days=30,
                    retirement_criteria=(
                        "DNSFilter removes or materially changes the mapped MCP tool.",
                        "A safer provider-supported administrative path replaces MCP.",
                    ),
                    last_reviewed_at=now,
                    operational_owner="AOT Managed Services",
                    approval_owner="AOT Owner",
                    authoritative_change_sources=(
                        "DNSFilter MCP connector documentation",
                        "DNSFilter MCP public tool catalog",
                    ),
                ),
                created_at=now,
                metadata={
                    "provider_neutral": "true",
                    "read_only": "false",
                    "write_capability": "true",
                    "activation_state": "source_only_not_registered",
                    "pilot_provider": "dnsfilter_mcp",
                    "provider_tool": tool_name,
                    "provider_confirmation_required": "true",
                    "explicit_human_approval_required": "true",
                    "user_disruptive_possible": (
                        "true"
                        if capability_name in _USER_DISRUPTIVE
                        else "false"
                    ),
                },
            )
        )
    return tuple(definitions)
