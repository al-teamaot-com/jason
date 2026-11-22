# Offline Ticket Context Augmentation — partial JSON read-only classification

## Section Goal
Preserve the existing legacy offline ticket/site-context classifier in a
canonical PMv4 JSON **read-only** candidate, reusing the current governed
ObservePort and existing legacy classifier functions, without modifying
production Ticket Core, invoking provider writes, creating a duplicate worker,
or altering PMv4 Stage E.

## Scope and source
- Source: `docs/playbooks/Jason-Offline-Ticket-Context-Augmentation.md`
- Legacy production registry: `offline_ticket_context_augmentation@0.1.0`,
  active pilot `autonomy.activation=shadow`.
- Source blob: `1af96e8b0cdd22fd24a60bf3841711cf1ab8b8c9`.
- Read-only JSON candidate:
  `candidates/offline_ticket_context_augmentation.v1.json`,
  `0.1.0-migration.2`, fingerprint
  `feeb7e6e0379487f65906a712d1955d1e7da97769ce6a57aaaa17a91f82dd698`.
- No Autotask note, status, queue or assignment changes. No endpoint
  remediation, contact change or external communication.

## Reused governed architecture
The exact preproduction builder
`jason_runtime/json_offline_context_preprod.py` loads the immutable
**draft** via the existing read-only JSON registry and binds the existing
`GovernedAutonomyReadPort` to the client. The JSON interpreter directs
five reads: exact Autotask ticket, exact same-company active configuration
item, exact DRMM endpoint, optional same-company DEB asset information, and
same-site peer inventory.

The fact reducer `json_offline_context_facts.py` enforces ticket ID and
company, CI ID/company/active, exact DRMM UID/hostname and site UID, and
each peer's site UID. Missing identity, cross-client/site evidence, and
unbounded peer lists fail closed. It reuses the legacy
`is_offline_ticket`, `SiteContextEvidence`,
`OperationalAutonomyMaintenance._offline_augmentation_role`,
`classify_site_context`, `render_site_context_note`, and existing
`select_deb_asset`. The note is a **preview fact only**, never sent.

## Isolated acceptance
- `test_json_offline_context_shadow.py`: five site classifications
  including two fixed peers online, two fixed peers offline, mobile
  exclusion, unknown case; compares exact assessment fingerprint and
  rendered legacy text. Includes same-client ticket and CI tests,
  same-site peer protection, oversized inventory, bad trigger, seed
  authority bypass and no repeated reads after completion.
- `test_json_offline_context_preprod.py`: existing governed ObservePort
  composition with synthetic request factory/Central Orchestrator;
  exact draft fingerprint, disabled/inert construction, and zero
  provider mutations.
- These are isolated simulated provider tests, not live client/provider
  acceptance.

## Not-yet-converted behavior — blocking
The actual legacy workflow additionally performs conditional peer role
refresh, one active fixed-server `Get-NetIPConfiguration` witness,
DEB unavailable/ambiguous fallback, a 10-minute cadence with source-version
rechecks, managed internal note deduplication and the Owner-promoted
`service.ticket.note.create` governed action plus authoritative note
readback. These are not implemented in this read-only candidate.

This candidate establishes **partial classifier parity only**.
It is NOT a fully accepted legacy replacement, does not authorize staging
in production, is not a live shadow dispatch path and does not change
the ledger's accepted count. Existing legacy remains enabled.

## Section Goal closure
Source read-only classifier and isolated consumer proof: PASS when
the exact CI revision validates. Full authored workflow parity and
real-provider acceptance: INCOMPLETE. Production activation and legacy
retirement: NOT AUTHORIZED.
