"""Source-only constitutional guard for migration to existing Teams services.

The config is an audited *inventory*, not a runtime feature switch. Tests never
send Teams messages, approve actions or access production provider credentials.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config/communications/teams-workflow-migration-v1.json"
RUNTIME = ROOT / "implementation/runtime_service/src/jason_runtime"
MCP = ROOT / "implementation/mcp_service/src/jason_mcp"
GRAPH = ROOT / "implementation/connectors/microsoft_graph"

REQUIRED_WORKFLOWS = {
    "signed_teams_conversation",
    "governed_staff_messages",
    "owner_nonexecuting_uat",
    "playbook_autonomy_review",
    "production_release_approval",
    "procurement_teams_forms",
    "procurement_approval",
    "mcp_invoice_review",
    "billing_disposition",
    "autonomous_completion",
    "universal_bounded_plan",
    "legacy_graph_approval_channel",
    "legacy_openclaw_approval_channel",
}


def inventory() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_reuses_existing_communications_approval_and_interaction_contracts():
    data = inventory()
    assert data["schema_version"] == "1.0"
    assert data["status"] == "source_inventory_only_not_runtime_configuration"
    assert (ROOT / data["owning_adr"]).is_file()
    assert (ROOT / data["governing_adr"]).is_file()
    required = {
        "interaction_contract",
        "interaction_orchestration",
        "teams_adapter",
        "teams_transport",
        "gateway",
        "approval_service",
        "approval_dispatcher",
        "identity_policy",
    }
    assert set(data["canonical"]) == required
    for path in data["canonical"].values():
        assert (ROOT / path).is_file(), path
    # The two existing capabilities are distinct. Both already exist.
    assert "JasonTeamsCommunicationService" in (
        ROOT / data["canonical"]["teams_transport"]
    ).read_text(encoding="utf-8")
    assert "ApprovalRequestService" in (
        ROOT / data["canonical"]["approval_service"]
    ).read_text(encoding="utf-8")
    assert "UniversalInteractionService" in (
        ROOT / data["canonical"]["interaction_orchestration"]
    ).read_text(encoding="utf-8")


def test_registered_workflows_have_unique_stable_adaptation_and_scope():
    data = inventory()
    flows = data["workflows"]
    assert {w["id"] for w in flows} == REQUIRED_WORKFLOWS
    assert len(flows) == len(REQUIRED_WORKFLOWS)
    for flow in flows:
        assert set(flow) == {
            "id", "source", "role", "channel", "approval", "migration",
            "wave", "risk", "rollout", "notes",
        }
        assert (ROOT / flow["source"]).is_file(), flow["source"]
        assert type(flow["wave"]) is int and 0 <= flow["wave"] <= 4
        assert flow["rollout"] in {
            "existing_production", "adapter_only", "accepted_test_only",
            "parity_only", "source_only", "unknown_usage",
        }
        assert flow["risk"] in {"low", "medium", "high", "critical"}
        assert len(flow["notes"].strip()) >= 15
        assert flow["approval"].strip()
        assert flow["migration"].strip()
        # This catalog is not a live routing/authorization store.
        assert not any(key in flow for key in (
            "enabled", "allow_execute", "owner_approval", "production_write",
            "provider_token", "channel_secret",
        ))
    high_risk = {w["id"] for w in flows if w["risk"] in {"critical", "high"}}
    assert "production_release_approval" in high_risk
    assert "procurement_approval" in high_risk
    assert "universal_bounded_plan" in high_risk
    assert next(w for w in flows if w["id"] == "owner_nonexecuting_uat")["wave"] == 0


def test_templates_reuse_existing_semantic_palette_without_per_workflow_colors():
    data = inventory()
    palette = data["presentation"]["semantic_colors"]
    assert palette == {
        "information": "Accent",
        "action_required": "Warning",
        "caution": "Warning",
        "critical": "Attention",
        "success": "Good",
    }
    templates = data["presentation"]["templates"]
    assert len(set(templates)) == len(templates)
    assert {"notice", "progress", "approval", "questionnaire", "incident"} <= set(templates)
    assert "one" in data["presentation"]["branding"]
    assert "no authority" in data["presentation"]["authority_notice"]
    adapter = (ROOT / data["canonical"]["teams_adapter"]).read_text(encoding="utf-8")
    for color in palette.values():
        assert f'"{color}"' in adapter
    for flow in data["workflows"]:
        assert "color" not in flow
        assert "style" not in flow
        assert "card_json" not in flow


def test_catalog_cannot_activate_runtime_or_change_owner_approval():
    data = inventory()
    assert data["rollout_rules"] == {
        "source_only": True,
        "no_runtime_feature_auto_activation": True,
        "deploy_requires_existing_exact_sha_owner_approval": True,
        "one_test_workflow_at_a_time": True,
        "no_direct_provider_or_execution_bypass": True,
        "no_automatic_retry_on_unknown_send": True,
        "tenant_and_client_boundary_required": True,
        "approval_callback_must_use_existing_signed_dispatcher": True,
        "legacy_retirement_requires_zero_live_consumers": True,
    }
    # This is a source inventory, not an executable production policy.
    composition = (RUNTIME / "composition.py").read_text(encoding="utf-8")
    assert "teams-workflow-migration-v1.json" not in composition
    assert "JASON_UNIVERSAL_APPROVAL_MODE=on" not in json.dumps(data)


def test_no_new_direct_python_http_sender_without_inventory_and_review():
    # One canonical wrapper plus TWO observed legacy direct callers.
    # Deliberately restrict to production Python, excluding tests/docs.
    seen = set()
    for tree in (RUNTIME, MCP):
        for path in tree.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if '"/internal/proactive/send"' in source:
                seen.add(path.relative_to(ROOT).as_posix())
    allowlisted = set(inventory()["direct_gateway_http_exceptions"])
    assert len(allowlisted) == 3
    assert seen == allowlisted, (
        "An unreviewed direct Teams sender or a retired legacy sender changed: "
        + str(sorted(seen ^ allowlisted))
    )
    assert "implementation/mcp_service/src/jason_mcp/server.py" in seen
    assert "implementation/runtime_service/src/jason_runtime/autonomous_completion_notification.py" in seen


def test_existing_raw_card_builders_are_inventory_only_retirement_exceptions():
    seen = set()
    for tree in (RUNTIME, GRAPH):
        for path in tree.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if '"type": "AdaptiveCard"' in source:
                seen.add(path.relative_to(ROOT).as_posix())
    allowed = set(inventory()["presentation"]["legacy_card_renderer_sources"])
    assert len(allowed) == 7
    assert seen == allowed, (
        "An unreviewed Teams card renderer or migrated renderer changed: "
        + str(sorted(seen ^ allowed))
    )
    # Source-only explicit exception is NOT permission to keep creating
    # divergent cards after the workflow's migration is accepted.
    for path in allowed:
        assert (ROOT / path).is_file()


def test_no_secondary_gateway_bot_or_approval_database_in_catalog():
    data = inventory()
    assert list(data["canonical"]).count("gateway") == 1
    assert "approval_service" in data["canonical"]
    assert "approval_dispatcher" in data["canonical"]
    for flow in data["workflows"]:
        assert flow["migration"] not in {
            "second_bot", "raw_gateway_send", "new_approval_ledger",
            "unscoped_approval", "direct_execution",
        }
