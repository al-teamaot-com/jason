# Jason Governed Teams Proactive Send Proof — 2026-09-18

## Section Goal
Enable Jason to send proactive Microsoft Teams messages through the existing direct Teams gateway under Jason governance.

## Production Result
- Capability: `communication.teams.message.send`
- Provider: `microsoft_teams_gateway`
- `direct_provider_access=false`
- Tenant isolation required.
- Previously authenticated Teams conversation references are persisted by AAD object identity and tenant.
- Governed send completed with exactly one provider attempt.
- Correlation: `corr_mcp_action_6db717b176974460a518e654ce40de75`
- Microsoft Teams message ID: `1789767399262`
- Gateway evidence: `jason_teams_proactive_sent`
- Source commit: `ad5b23be24356827530264e692c3a0161e4259a7`

## Acceptance
PASS. A harmless proactive outbound Teams message was sent to the authenticated owner conversation after the gateway captured a fresh post-deployment conversation reference. The governed capability returned `status=succeeded`, `stage=completed`, `provider_attempts=1`; the gateway independently recorded the Microsoft Teams message ID.

## Approval and information-request extension

The same governed outbound path was extended on 2026-09-18 to accept a bounded Adaptive Card payload while preserving `communication.teams.message.send`, tenant isolation, exact Jason authority, Central Orchestrator routing, and `direct_provider_access=false`.

Production acceptance established:

- proactive Adaptive Card delivery through the authenticated direct Teams gateway — **PASS**;
- harmless Approve/Deny card presented to the authenticated owner conversation — **PASS**;
- Teams button interaction returned to the Jason gateway — **PASS**;
- Microsoft tenant and AAD object identity authenticated at Jason ingress — **PASS**;
- final approval-decision processing — **BLOCKED** by external OpenAI API `429 insufficient_quota / credit_balance_exhausted`.

During this acceptance, an independent runtime compatibility defect was also found and corrected: `gpt-5.4-mini` rejected `reasoning.effort=minimal`; Jason now uses supported `low` effort. The correction is source commit `811b3af` and was deployed to the conversation runtime before the final retry.

The remaining work is governed as `TODO-COMM-004`. The workflow must not be represented as fully production-accepted until, after API credit availability is restored, a fresh harmless card proves exact approval-ID correlation through terminal decision processing and separate tests prove a structured information request and typed override. A typed override is a modified instruction, not implicit approval.

## Section Goal closure

**PARTIAL / BLOCKED.** The original Section Goal—governed proactive Teams message sending—is complete and production-proven. The follow-on interactive approval/information-request Section Goal is implemented through authenticated ingress but remains blocked at final decision processing by the external OpenAI API credit balance. No operational action was authorized or executed by the harmless approval-card test.
