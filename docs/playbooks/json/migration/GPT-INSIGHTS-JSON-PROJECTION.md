# GPT Insights — guarded JSON source projection candidate

## Section Goal
Preserve the deployed pure technician-assist classifier, recommendation
renderer and material evidence deduplication in a source-bound PMv4 JSON
candidate without touching Ticket Core, introducing provider authority, or
generating a production note.

## Source and scope
Original: `gpt_insights_tech_assist@0.2.1`,
`docs/playbooks/Jason-GPT-Insights-Tech-Assist.md`.
JSON: `candidates/gpt_insights_tech_assist.v1.json`,
`0.2.1-migration.2`.
Canonical fingerprint:
`2f7f8c15d3e233284270e55a38a838cf7a09ff11ddc1c08ef81a2915e280fe51`.

The current source `gpt_insights.py` provides category identification,
evidence material fingerprint and deterministic technician-facing note text.
`json_gpt_insights_projection.py` reuses those pure functions and
`managed_ticket_notes` to prepare a create/update/noop intent, but never
executes a provider action or creates a grant.

Scope: exact same-client Help Desk I, status New, non-Recurring ticket;
one Jason-owned internal note, with `noteType=3` and `publish=2`.
No ticket assignment/queue/status change, client notification, endpoint
operation or disruptive action.

## Independent synthetic verification
`test_json_gpt_insights_projection.py` proves categories network,
printing, performance, login, application and unknown match deployed
classifier; provider note body/fingerprint matches current renderer.
Fail-closed cases cover excluded queues/status/source, duplicate title,
client mismatch, creator mismatch, client-visible note, wrong ticket,
missing source state, unverified endpoint, and missing/paginated note list.
Database-loss with an existing base note seeds state without a new write.
The JSON interpreter's create/update branches require exact governed
promotion facts; no permission originates in JSON.

## Remaining full parity
- Governed source queue/status and explicit Recurring exclusion through a
  current client-bound ticket read.
- Same-company CI, endpoint and optionally network PowerShell source read,
  related ticket correlation and trusted evidence normalization.
- Existing augmentation SQLite fingerprint/cadence and material source
  version changes connected to the common JSON persisted state.
- Owner-promoted note create/update, exact Jason creator check and
  post-mutation readback/audit in independent preproduction.
- No production activation until a separately approved source SHA, full
  behavior parity and cutover/rollback verification.

**Pure classifier and projection: synthetic PASS.**
**Full legacy parity and provider-connected acceptance: NOT VERIFIED.**
**Accepted replacement: NO.** Production remains unchanged.
