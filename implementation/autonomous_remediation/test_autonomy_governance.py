from datetime import datetime, timedelta, timezone

from .autonomy_governance import (
    ActionContext,
    AuthorityGrant,
    GovernanceEngine,
    GovernanceOutcome,
    GovernanceRule,
    GovernanceScope,
)


def context(**overrides):
    values = {
        "capability": "endpoint.reboot.schedule",
        "ticket_id": "T1",
        "action_fingerprint": "sha256:exact-plan",
        "site_id": "SITE1",
        "device_id": "DEV1",
        "user_id": "USER1",
        "playbook_id": "disk-space",
        "disruptive": True,
    }
    values.update(overrides)
    return ActionContext(**values)


def test_global_disruptive_rule_requires_exact_ticket_authority():
    engine = GovernanceEngine([
        GovernanceRule(
            "global-disruption-approval",
            GovernanceScope.GLOBAL,
            GovernanceOutcome.REQUIRE_APPROVAL,
            disruptive_only=True,
        )
    ])
    decision = engine.evaluate(context())
    assert decision.outcome == GovernanceOutcome.REQUIRE_APPROVAL
    assert not decision.may_execute


def test_exact_ticket_grant_satisfies_approval():
    engine = GovernanceEngine([
        GovernanceRule(
            "global-disruption-approval",
            GovernanceScope.GLOBAL,
            GovernanceOutcome.REQUIRE_APPROVAL,
            disruptive_only=True,
        )
    ])
    grant = AuthorityGrant(
        "approval-1",
        "T1",
        "endpoint.reboot.schedule",
        "sha256:exact-plan",
        device_id="DEV1",
    )
    decision = engine.evaluate(context(), grants=[grant])
    assert decision.outcome == GovernanceOutcome.ALLOW
    assert decision.authority_grant_id == "approval-1"


def test_grant_cannot_be_replayed_on_another_device_or_action():
    engine = GovernanceEngine([
        GovernanceRule(
            "global-disruption-approval",
            GovernanceScope.GLOBAL,
            GovernanceOutcome.REQUIRE_APPROVAL,
            disruptive_only=True,
        )
    ])
    grant = AuthorityGrant(
        "approval-1",
        "T1",
        "endpoint.reboot.schedule",
        "sha256:exact-plan",
        device_id="DEV1",
    )
    assert engine.evaluate(context(device_id="DEV2"), grants=[grant]).outcome == GovernanceOutcome.REQUIRE_APPROVAL
    assert engine.evaluate(context(action_fingerprint="sha256:different"), grants=[grant]).outcome == GovernanceOutcome.REQUIRE_APPROVAL


def test_expired_grant_is_not_authority():
    now = datetime.now(timezone.utc)
    engine = GovernanceEngine([
        GovernanceRule(
            "global-disruption-approval",
            GovernanceScope.GLOBAL,
            GovernanceOutcome.REQUIRE_APPROVAL,
            disruptive_only=True,
        )
    ])
    grant = AuthorityGrant(
        "approval-1",
        "T1",
        "endpoint.reboot.schedule",
        "sha256:exact-plan",
        expires_at=now - timedelta(seconds=1),
    )
    assert engine.evaluate(context(), grants=[grant], now=now).outcome == GovernanceOutcome.REQUIRE_APPROVAL


def test_more_restrictive_device_rule_wins():
    engine = GovernanceEngine([
        GovernanceRule("global-allow", GovernanceScope.GLOBAL, GovernanceOutcome.ALLOW),
        GovernanceRule(
            "protected-server",
            GovernanceScope.DEVICE,
            GovernanceOutcome.BLOCK,
            device_id="DEV1",
            reason="Protected production system",
        ),
    ])
    decision = engine.evaluate(context(disruptive=False))
    assert decision.outcome == GovernanceOutcome.BLOCK
    assert "protected-server" in decision.matched_rule_ids


def test_authority_grant_never_overrides_a_block():
    engine = GovernanceEngine([
        GovernanceRule("global-allow", GovernanceScope.GLOBAL, GovernanceOutcome.ALLOW),
        GovernanceRule("device-block", GovernanceScope.DEVICE, GovernanceOutcome.BLOCK, device_id="DEV1"),
    ])
    grant = AuthorityGrant(
        "approval-1",
        "T1",
        "endpoint.reboot.schedule",
        "sha256:exact-plan",
        device_id="DEV1",
    )
    assert engine.evaluate(context(), grants=[grant]).outcome == GovernanceOutcome.BLOCK


def test_no_rule_fails_closed():
    decision = GovernanceEngine([]).evaluate(context())
    assert decision.outcome == GovernanceOutcome.BLOCK


def test_consumed_single_use_grant_cannot_be_replayed():
    now = datetime.now(timezone.utc)
    engine = GovernanceEngine([
        GovernanceRule(
            "global-disruption-approval",
            GovernanceScope.GLOBAL,
            GovernanceOutcome.REQUIRE_APPROVAL,
            disruptive_only=True,
        )
    ])
    grant = AuthorityGrant(
        "approval-1",
        "T1",
        "endpoint.reboot.schedule",
        "sha256:exact-plan",
        consumed_at=now - timedelta(seconds=1),
    )
    assert engine.evaluate(context(), grants=[grant], now=now).outcome == GovernanceOutcome.REQUIRE_APPROVAL
