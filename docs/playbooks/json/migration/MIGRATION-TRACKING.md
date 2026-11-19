# Legacy Markdown/Python to JSON migration — source-only tracking

## Section Goal
Migrate the verified legacy registry to canonical PMv4 JSON without production activation, bypassing legacy paths, or colliding with PMv4 Stage E. Success means each legacy source is reconciled to an independently schema/semantic/branch/approval/retry/recovery/parity/shadow-tested version with immutable source and target evidence.

## Scope and baseline
- Legacy registry: `implementation/autonomous_remediation/playbook_registry.json`. On the inspected source revision it contains **19 enabled records** (18 Markdown, 1 Python). The exact source hashes and source-mapping signals are in `legacy-inventory-20261119.json` and `source-audit-20261119.json`.
- The installed production JSON registry was separately read through Jason MCP on 2026-11-19; returned **generation 0, no playbooks**. No draft staging, JSON activation, retirement, or provider mutation is authorized by this source-only workstream.
- The production Ticket Core is protected, and existing legacy dispatch must remain unchanged. PMv4 Stage E and its root authority, release control, and systemd configuration are out of scope.
- GitHub branch: `feat/legacy-json-migration-20261119` (independent from PMv4 Stage E).

## Current gates and outstanding incompatibilities
The existing `playbook-v1.schema.json`, `playbook_document.py`, and `playbook_runtime.py` provide versioned deterministic instruction interpretation, not complete execution semantics:
1. A decision step consumes externally supplied fact values; the interpreter neither obtains fresh facts nor verifies provenance. An authorized caller must populate facts from exact same-company and same-ticket governed operations. A synthetic true value is **not** proof of identity or Owner authorization.
2. No state machine executor is provided by the interpreter to persist every step, track action IDs, derive provider readback facts, enforce dedupe, retry backoff, or recover after interruption. These are shared runtime obligations; per-playbook JSON annotation alone does not implement them.
3. The graph validator expressly rejects cycles. Many legacy workflows need repeated wait/recheck and bounded remedial retry. A scheduled re-entry/persisted resume contract must be proven in the existing worker/JSON runtime before parity.
4. JSON metadata can name approval classifications, but only existing service-identity Central Orchestrator and exact Owner-bound policy grants can authorize an action. Do not elevate draft metadata, a caller-supplied Boolean, or a source-defined allowlist to execution authority.
5. Built-in graph `complete` means terminal instruction emitted, not independently proven PSA ticket resolution. Protected process, provider, and client readbacks are still required.
6. Python-driven Datto EDR/AV logic, conditional multi-provider correlations, ticket-note ownership, client notifications, and multi-device fanout must be individually traced to governed capabilities or a reusable, separately tested adapter—not replaced with invented provider calls.

## Candidate status
- `candidates/unsupported_readonly_triage_note.v1.json`: **source-only, NOT migration accepted**. Lower-risk evidence/note pilot; synthetically verifies exact pilot allowlist, company/source/assignment checks, note ownership, duplicate suppression, separate promotion, provider readback and candidate write arguments. However the legacy Python gather/classifier, durable worker retries and provider-approved note execution are not yet backed by the JSON execution adapter. Its `shadow` setting does not grant any write authority.
- `candidates/drmm_recent_alert_reconciliation.v1.json`: **source-only, NOT migration accepted**. Mapped the implemented daily DRMM security-alert verifier and exact alert/ticket actions. Controlled same-fixture legacy-worker-vs-JSON tests cover older-than-24-hours, unsupported alert class, offline device, active detection, and exact successful alert/ticket action intents. The current interpreter does not implement durable daily cadence, multi-alert iteration, trusted read-result fact mapping, or receipt-backed authorization, so this remains unaccepted. No alert or ticket was mutated.
- `candidates/unsupported_triage_human_review.v1.json`: **source-only, NOT migration accepted**. Uses `1.0.0-migration.1` to avoid replacing the legacy `1.0.0`. Negative gates and staged draft persistence are synthetically tested. The exact legacy `service.ticket.update` payload is now preserved: `{payload:{id,queueID:"Help Desk I",status:"Human Review"}}`; runtime wiring, live current-state fact supply, dedupe, delay/retry, and actual provider parity are **not verified**. Production activation prohibited.
- Candidate synthetic tests are in `tests/test_legacy_json_migration_candidate.py`. Controlled same-fixture intent comparisons against the **actual existing legacy worker** are in `tests/test_legacy_json_behavioral_parity.py` (positive and negative handoff conditions, plus exact internal note-create payload). The IDs are rewritten only in an in-memory test copy of the JSON to match existing synthetic legacy worker fixtures; versioned production-scope candidate files are not modified. This is **narrow action-intent parity**, not a full end-to-end workflow, interrupted-recovery, or operational shadow acceptance. Passing these tests does not promote `autonomy.activation`.

## Required acceptance, each independently recorded
For each original playbook ID:
1. Freeze the exact legacy source revision and compare it to the registry entry, including client-override/conditional paths.
2. Preserve trigger, Section Goal, target identity, expected state, state transitions, dependencies, retries, wait/rechecks, note/audit, authority, escalation, and independent verification.
3. Confirm every invoked capability is registered and actually governed. Treat missing capability or unsupported interpreter syntax as blocking, not silently discard.
4. Validate canonical JSON with Draft 2020-12 schema and Python semantic validator against the exact registered capability set.
5. Run positive, negative, identity/tenant/approval denial, idempotency, interrupted-resume, stale-read, and exact-terminal-readback tests.
6. Compare the same synthetic fixtures against legacy and JSON paths; capture matched decisions, arguments, side-effect intents, persisted state transitions, notes, and terminal conditions.
7. Isolated shadow acceptance must demonstrate no provider writes, exact context identity, verified output, safe recovery, and no duplicate active dispatch path.
8. Record immutable candidate SHA, source SHA, test results, acceptance disposition, and remaining gaps. Count accepted **only after all gates pass**.

## Production activation / rollback plan (not authorized)
- Keep the legacy playbook enabled during candidate conversion, tests, draft staging, and shadow execution.
- After exact-scope acceptance and verified Owner approval, atomically select the JSON version in the existing production registry under the service identity, verify generation/audit/readback, and ensure the old legacy dispatcher does **not** concurrently execute it.
- Canary one playbook at a time, with verified ticket and provider readbacks, and verify protected Ticket Core and unrelated workflows remain healthy.
- If acceptance or health fails, restore the previous selection and dispatch policy using exact authorized rollback, verify active versions and audit history, preserve the legacy definition, and document the incident. Registry rollback alone does not prove the legacy dispatch control was restored.
- Retire legacy definitions only after separately approved sustained parity and rollback evidence. Never delete historical artifacts as part of candidate source migration.

## Reconciliation and progress accounting
- **19/19** registry source records independently located and hashed.
- **0/19** playbooks accepted as behaviorally equivalent; acceptance requires runtime-path integration and shadow evidence, not only passing tests.
- No production JSON activation, main merge, legacy retirement, Stage E modification, or core restart.
- Remaining status is tracked as explicit incomplete work, not implicitly promoted.

## Follow-up engineering
Implement/verify a **single reusable governed JSON state/fact adapter inside the existing runtime orchestration path** with strict source provenance and immutable exact approval evidence; do not make a parallel engine. Work through one low-risk read-only/shadow candidate, then independently convert and test the entire inventory in batches while Stage E continues.

## Verified current source exceptions and reusable compatibility work
- **BackupIQ version drift**: the enabled legacy registry selects `backupiq_endpoint_backup@1.2.0`, while its source Markdown explicitly declares `1.3.0`. Preserve both exact source and registry hashes. Do not change production selection or silently assume the later text is an approved version. The reproducible inventory audit and source test detect this discrepancy. Other parsable explicit source manifest versions matched registry versions at this source revision.
- `implementation/autonomous_remediation/playbook_ticket_evidence.py` is a new reusable **read-only exact-identity guard** for the two unsupported-triage candidates. It normalizes *existing governed-read response envelopes* and rejects ticket ID, company, queue, status, assignment, ownership, pilot ID, note identity or note body mismatches. It **does not** mint Owner promotion, action authority or successful post-mutation readback evidence. It does not call providers. Source-only tests are in `tests/test_playbook_ticket_evidence.py`.
- `implementation/autonomous_remediation/playbook_document.py` now rejects non-list JSON membership condition operands. `playbook_runtime.py` skips negative-operator decision branches when a fact is absent. These shared fail-closed corrections are source-only and separately regression-tested.
- `tools/json_playbook_isolated_trace.py`, `fixtures/` and `evidence/` record deterministic synthetic traces for the three JSON candidates. The trace utility **never executes a capability**, grants approval, stages a registry or activates a playbook. Six fixtures cover positive and negative branches. These traces are **isolated test evidence**, not authenticated live shadow or operational acceptance.
- All three drafts have been validated through Jason's live **read-only validation endpoint**; the independent production JSON registry remained at **generation 0 with no versions** on the observed readback.

## Mandatory runtime integration boundary
The currently deployed JSON Runbook Management can validate and store immutable JSON definitions, but the inspected source interpreter itself does not supply runtime fact provenance, iterative multi-ticket/multi-alert execution, durable step scheduling/retry state, exact approval binding or provider verification. Reimplementing those ad hoc in each JSON definition would create unsafe duplicate execution paths and violate the project's shared-capability architecture. The reusable fact guard is an initial source-only capability, **not** a complete replacement for those missing services. No production Ticket Core change is authorized. Complete shared JSON execution/fact/state integration through a separately governed component interface and prove it with isolated end-to-end acceptance before any candidate is counted ready; preserve PMv4 Stage E isolation.
