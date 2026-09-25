"""Provider-neutral governance resolution for autonomous Jason work.

Operational evidence never creates authority. Authority is represented only by
explicit governance rules and narrowly bound grants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from fnmatch import fnmatch
from typing import Iterable


class GovernanceScope(str, Enum):
    GLOBAL = "global"
    SITE = "site"
    DEVICE = "device"
    USER = "user"
    TICKET = "ticket"


class GovernanceOutcome(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


_OUTCOME_RANK = {
    GovernanceOutcome.ALLOW: 0,
    GovernanceOutcome.REQUIRE_APPROVAL: 1,
    GovernanceOutcome.BLOCK: 2,
}


@dataclass(frozen=True)
class ActionContext:
    capability: str
    ticket_id: str
    action_fingerprint: str
    site_id: str | None = None
    device_id: str | None = None
    user_id: str | None = None
    playbook_id: str | None = None
    disruptive: bool = False


@dataclass(frozen=True)
class GovernanceRule:
    rule_id: str
    scope: GovernanceScope
    outcome: GovernanceOutcome
    capability_pattern: str = "*"
    site_id: str | None = None
    device_id: str | None = None
    user_id: str | None = None
    ticket_id: str | None = None
    disruptive_only: bool = False
    reason: str = ""

    def applies_to(self, context: ActionContext) -> bool:
        if not fnmatch(context.capability, self.capability_pattern):
            return False
        if self.disruptive_only and not context.disruptive:
            return False
        selectors = (
            (self.site_id, context.site_id),
            (self.device_id, context.device_id),
            (self.user_id, context.user_id),
            (self.ticket_id, context.ticket_id),
        )
        return all(expected is None or expected == actual for expected, actual in selectors)


@dataclass(frozen=True)
class AuthorityGrant:
    """A temporary, explicit grant bound to the exact intended action."""

    approval_id: str
    ticket_id: str
    capability: str
    action_fingerprint: str
    device_id: str | None = None
    site_id: str | None = None
    user_id: str | None = None
    expires_at: datetime | None = None
    single_use: bool = True
    consumed_at: datetime | None = None

    def matches(self, context: ActionContext, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.single_use and self.consumed_at is not None:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        if self.ticket_id != context.ticket_id:
            return False
        if self.capability != context.capability:
            return False
        if self.action_fingerprint != context.action_fingerprint:
            return False
        selectors = (
            (self.device_id, context.device_id),
            (self.site_id, context.site_id),
            (self.user_id, context.user_id),
        )
        return all(expected is None or expected == actual for expected, actual in selectors)


@dataclass(frozen=True)
class GovernanceDecision:
    outcome: GovernanceOutcome
    matched_rule_ids: tuple[str, ...] = ()
    authority_grant_id: str | None = None
    reasons: tuple[str, ...] = ()

    @property
    def may_execute(self) -> bool:
        return self.outcome == GovernanceOutcome.ALLOW


class GovernanceEngine:
    """Resolve global/site/device/user/ticket policy without evidence-based authority."""

    def __init__(self, rules: Iterable[GovernanceRule]) -> None:
        self._rules = tuple(rules)

    def evaluate(
        self,
        context: ActionContext,
        *,
        grants: Iterable[AuthorityGrant] = (),
        now: datetime | None = None,
    ) -> GovernanceDecision:
        matched = tuple(rule for rule in self._rules if rule.applies_to(context))
        if not matched:
            return GovernanceDecision(
                GovernanceOutcome.BLOCK,
                reasons=("No governance rule authorizes this action.",),
            )

        strictest = max(matched, key=lambda rule: _OUTCOME_RANK[rule.outcome]).outcome
        matched_ids = tuple(rule.rule_id for rule in matched)
        reasons = tuple(rule.reason for rule in matched if rule.reason)

        if strictest == GovernanceOutcome.BLOCK:
            return GovernanceDecision(strictest, matched_ids, reasons=reasons)

        if strictest == GovernanceOutcome.REQUIRE_APPROVAL:
            for grant in grants:
                if grant.matches(context, now=now):
                    return GovernanceDecision(
                        GovernanceOutcome.ALLOW,
                        matched_ids,
                        authority_grant_id=grant.approval_id,
                        reasons=reasons + ("Exact ticket/incident authority grant satisfied approval.",),
                    )
            return GovernanceDecision(strictest, matched_ids, reasons=reasons)

        return GovernanceDecision(strictest, matched_ids, reasons=reasons)
