import pytest

from connectors.microsoft_graph.teams_approval_targets import (
    TeamsApprovalTargetRecord,
    TeamsApprovalTargetRegistry,
)


def test_resolves_only_exact_organization_target():
    registry = TeamsApprovalTargetRegistry.from_records([
        TeamsApprovalTargetRecord("org-a", "team-a", "channel-a"),
        TeamsApprovalTargetRecord("org-b", "team-b", "channel-b"),
    ])

    target = registry.resolve(organization_id="org-a")

    assert target is not None
    assert target.organization_id == "org-a"
    assert target.team_id == "team-a"
    assert target.channel_id == "channel-a"


def test_missing_target_fails_closed_as_none():
    registry = TeamsApprovalTargetRegistry.from_records([
        TeamsApprovalTargetRecord("org-a", "team-a", "channel-a"),
    ])

    assert registry.resolve(organization_id="org-b") is None


def test_disabled_target_is_not_resolved():
    registry = TeamsApprovalTargetRegistry.from_records([
        TeamsApprovalTargetRecord("org-a", "team-a", "channel-a", enabled=False),
    ])

    assert registry.resolve(organization_id="org-a") is None


def test_duplicate_enabled_targets_are_rejected():
    with pytest.raises(ValueError, match="multiple enabled Teams approval targets"):
        TeamsApprovalTargetRegistry.from_records([
            TeamsApprovalTargetRecord("org-a", "team-a", "channel-a"),
            TeamsApprovalTargetRecord("org-a", "team-b", "channel-b"),
        ])


def test_disabled_duplicate_does_not_create_ambiguity():
    registry = TeamsApprovalTargetRegistry.from_records([
        TeamsApprovalTargetRecord("org-a", "team-a", "channel-a"),
        TeamsApprovalTargetRecord("org-a", "team-old", "channel-old", enabled=False),
    ])

    target = registry.resolve(organization_id="org-a")
    assert target is not None
    assert target.team_id == "team-a"


def test_invalid_records_are_rejected():
    with pytest.raises(ValueError):
        TeamsApprovalTargetRegistry.from_records([
            TeamsApprovalTargetRecord("", "team-a", "channel-a"),
        ])


def test_blank_lookup_is_rejected():
    registry = TeamsApprovalTargetRegistry.from_records([])
    with pytest.raises(ValueError, match="organization_id"):
        registry.resolve(organization_id="  ")
