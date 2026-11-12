"""MCP AOT group activation is Owner-only and requires a fresh exact approval."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from jason_mcp import server
from orchestrator.microsoft_group_admin_catalog import (
    AOT_PILOT_OWNER_PRINCIPAL_ID, AOT_PILOT_CLIENT_ID,
    AOT_PILOT_GROUP_NAME, AOT_PILOT_GROUP_ALIAS, AOT_PILOT_OWNER_ID,
)


def args():
    return {
        "display_name": AOT_PILOT_GROUP_NAME,
        "mail_nickname": AOT_PILOT_GROUP_ALIAS,
        "group_type": "security",
        "verified_owner_id": AOT_PILOT_OWNER_ID,
    }


def test_mcp_canonical_arguments_allow_only_approved_fields():
    assert server._canonicalize_governed_action_arguments(
        "identity.group.create", args()) == args()
    with pytest.raises(ValueError, match="unrecognized|Missing"):
        server._canonicalize_governed_action_arguments(
            "identity.group.create", {**args(), "raw_url": "https://graph.microsoft.com/users"})
    with pytest.raises(ValueError):
        server._canonicalize_governed_action_arguments(
            "identity.group.create", {**args(), "group_type": "dynamic"})


def test_mcp_non_owner_denied_before_authority_or_provider(monkeypatch):
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "_authenticated_write_identity",
                        lambda: ("person-entra-unapproved", "aot","entra-oauth-bearer", None))
    result=server._governed_execute(
        capability_name="identity.group.create", arguments=args(), explicit_approval=True)
    assert result["status"]=="denied"
    assert result["reason_codes"]==["M365_GROUP_PILOT_OWNER_OR_CLIENT_SCOPE_DENIED"]


def test_mcp_group_create_requires_explicit_owner_exact_action(monkeypatch):
    from kernel.identity_authority import AuthorityOutcome
    from types import SimpleNamespace
    capability=SimpleNamespace(
        metadata={"mcp_action_enabled":"true",
                  "conversation_authenticated_imperative_is_approval":"false"},
        approval=SimpleNamespace(required=True),
    )
    app=SimpleNamespace(
        capabilities=SimpleNamespace(get_current=lambda **kw: capability),
        identity_authority=SimpleNamespace(evaluate=lambda req: SimpleNamespace(
            outcome=AuthorityOutcome.APPROVAL_REQUIRED,reason_codes=("APPROVAL_REQUIRED",))),
    )
    monkeypatch.setattr(server, "_runtime", lambda: app)
    # Isolate approval binding in this test; the actual least-disruptive
    # remediation evidence gate is independently tested immediately below.
    monkeypatch.setattr(server, "applies_to_remediation", lambda _: False)
    monkeypatch.setattr(server, "_authenticated_write_identity", lambda: (
        AOT_PILOT_OWNER_PRINCIPAL_ID, "aot", "entra-oauth-bearer", None))
    result=server._governed_execute(
        capability_name="identity.group.create",arguments=args(),explicit_approval=False)
    assert result["status"]=="approval_required"
    assert result["capability"]=="identity.group.create"



def test_mcp_group_write_without_remediation_evidence_rejected_before_approval(monkeypatch):
    from kernel.identity_authority import AuthorityOutcome
    capability=SimpleNamespace(
        metadata={"mcp_action_enabled": "true"},
        approval=SimpleNamespace(required=True),
    )
    app=SimpleNamespace(
        capabilities=SimpleNamespace(get_current=lambda **kw: capability),
        identity_authority=SimpleNamespace(evaluate=lambda req: SimpleNamespace(
            outcome=AuthorityOutcome.APPROVAL_REQUIRED,
            reason_codes=("APPROVAL_REQUIRED",))),
    )
    monkeypatch.setattr(server, "_runtime", lambda: app)
    monkeypatch.setattr(server, "_authenticated_write_identity", lambda: (
        AOT_PILOT_OWNER_PRINCIPAL_ID, "aot", "entra-oauth-bearer", None))
    result=server._governed_execute(
        capability_name="identity.group.create",
        arguments=args(), explicit_approval=True,
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "REMEDIATION_ACTION_NOT_JUSTIFIED"
    assert "REMEDIATION_ASSESSMENT_REQUIRED" in result["reason_codes"]
