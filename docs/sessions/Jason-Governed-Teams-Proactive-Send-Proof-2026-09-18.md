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
