# Jason Teams card UX: approval and operational status (source-only)

**Status:** Engineering preview, not live. Parent #1440; design direction ADR-013. Reviewed source branch PR #1971. This is a presentation contract, not an authority policy or permission to deploy.

## Actual problem observed

On 2026-10-23 the production Jason Approval Bot sent a compact but generic Adaptive Card labelled *Jason production queue started* and a separate text notification describing the same release. Earlier owner approval cards put up to nine FactSet entries, including 40-character source/rollback identifiers and a manifest hash, **above** Approve/Deny on narrow mobile screens. Owner feedback: the Teams card appearance is unacceptable.

There are two separate problems:
1. **Presentation:** inconsistent visual hierarchy, excessive labels, long identifiers cramped into FactSet, and owner action hidden among metadata. This source preview addresses presentation only.
2. **Delivery duplication:** current autonomous completion path has separately observed text and card messages. The outgoing sender, one-attempt delivery and evidence receipts must be reviewed before eliminating those duplicates. This patch deliberately does *not* suppress one of the sends or imply that it does.

## AOT / Jason presentation, v1

Use the existing Adaptive Cards **v1.4** renderer, Microsoft Teams native semantic colors, and the existing signed gateway and transport. No new bot, card service, provider authorization, workflow or approval database.

### Actionable production approval

Visible without expanding details:
- **JASON · AOT**: small subdued brand identification.
- **Approval required**: prominent, warning-colored heading.
- Plain-language purpose (existing server-rendered release title).
- Exactly what Approve means: authorizes the **exact source release and CCC material review**, never immediate deployment.
- **Risk, independent checks and expiry**.
- **Full exact source SHA and rollback SHA** in separate wrapped monospace TextBlocks. Never truncate, replace, or rely only on short prefixes.
- Two explicit `Action.Submit` decisions: **Approve** and **Deny**, with semantic positive/destructive styles.

A `Action.ToggleVisibility` control titled **Review impact and evidence** reveals the original immutable review facts (release ID, affected systems, changed files, original manifest/policy digest and evidence reference IDs) inside the *same card*. The underlying approval request remains authoritative; displayed facts grant no authority. This is progressive disclosure only.

Never modify `approval_id`, `decision`, the optional v2 `card_challenge`, target approver, signed gateway verification, TTL, nonce/replay guard, CCC source binding or original protected deployment gates. Other playbook/owner-UAT approval renderers remain unchanged.

### Informational status / owner action cards

- Reuse the same small **JASON · AOT** identifier.
- Medium-weight semantic headline: `Accent` for informational, `Good` for completed, `Attention` for escalated.
- Full bounded summary still rendered.
- When and **only when** an Owner action exists, show a separate **NEXT ACTION** section above supporting facts. Never create Approve or Deny for a status-only card.
- Keep original metadata in a lower-priority FactSet; preserve existing event text and source facts.

### Canonical shadow parity boundary

The existing `autonomous_completion_teams_compatibility.py` preview is **not live**. It now validates the exact new brand header, title/color/summary/fact structure while retaining the same full underlying text and facts in the canonical Interaction. The existing AOT owner `person-al` route, message purposes, tenant/audience checks, idempotent one-send claim, no-action/no-client boundary and tamper rejection remain in force. This is *not* a generalized renderer acceptance policy.

## Required tests and shipping boundary

- 211 targeted host tests pass for status source, canonical Teams shadow parity, mobile release approval and challenge, Teams transport, playbook reviews, nonexecuting owner UAT, universal interactions and plan approval.
- Cross-language signed gateway `Action.Submit` parser tests pass.
- `git diff --check` passes.
- These are source semantics/contract tests, **not proof of actual visual appearance on the AOT Owner's Teams desktop/Android/iOS clients**.

Before activating later:
1. Confirm protected CI and independent exact-source review of this PR.
2. Capture a genuine Teams mobile and desktop card screenshot with long release purpose, full SHA/rollback, short and long metadata, expandable detail, warning/status states and two button decisions.
3. Prove callback identity, tenant, card instance challenge, expiry, one-time receipt, deny/replay and CCC/host independence without any customer/provider write.
4. Resolve the separate double-message delivery UX only via a proved no-duplicate/no-lost-notification sender rollout.
5. Obtain **new exact SHA owner approval and CCC** for this change. PR #1971 is a DRAFT: **do not merge/deploy while the already production-eligible `release-e8caace9791659ad` remains in the existing authorization pipeline**.
