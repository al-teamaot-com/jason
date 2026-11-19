# PMv4 JSON — isolated read-only shadow pilot acceptance

## Section Goal
Independently prove the existing PMv4 JSON **interpreter** can consume bounded
read-only, exact-target governed-read-style evidence through a shared
component without altering the protected production Core, executing a
remediation, creating a second playbook registry, or changing Stage E.

This is a **source-only, synthetic isolated acceptance** for a standalone
diagnostic pilot, not acceptance of any of the 19 legacy-to-JSON replacements.

## Exact pilot
- ID: `drmm_recent_alert_readonly_shadow_pilot`
- Version: `0.1.0`
- Definition: `candidates/drmm_recent_alert_readonly_shadow_pilot.v1.json`
- Semantic fingerprint: `0b537a13c70339e35f3d49a73f9c02689aa472b2f6e5d095ba7fc64bf270ef06`
- Source basis: `docs/playbooks/Jason-DRMM-Recent-Alert-Reconciliation.md`,
  source Git blob `076872fae94f49d3daa3dc1b8740bd99fee75ee2`
- Activation: `shadow`. This pilot does not replace or activate
  `drmm_recent_alert_reconciliation@1.0.0`.
- Scope: one exact alert UID and client-bound read port; no DRMM resolution,
  ticket note, ticket update, device component, or other provider mutation.

## Shared integration components
- `implementation/autonomous_remediation/json_shadow_integration.py`:
  uses `JsonPlaybookInterpreter` and, in isolated tests, the existing
  `SQLitePlaybookRegistry` for draft staging. Separate private SQLite
  **run checkpoint** is not a playbook registry. It persists facts derived
  from governed-read-style responses, source/version identity, step cursor,
  evidence hashes, wait due time, and result.
- `implementation/autonomous_remediation/json_shadow_facts.py`:
  exact alert UID, provider timestamp, supported class, endpoint UID,
  current online status, agent identity, AV readiness, current detections.
  Ambiguous, duplicate, absent or mismatched records are rejected.
- Existing `SQLitePlaybookAutonomyApprovalStore` can be queried in synthetic
  shadow for exact-version promotion; a positive result only yields a
  **proposed blocked mutation**. No authority fact is persisted; there is
  no mutating executor.
- An injected read-port client binding is required. The test port is
  in-memory and must **not** be treated as proof of live provider access.
- All user/caller seed facts except immutable client and target IDs are
  rejected. Missing read evidence, missing capability, stale fingerprint,
  cross-client resume and missing/ambiguous readbacks fail closed.

## Independent synthetic acceptance
Source: `tests/test_json_readonly_shadow_pilot_acceptance.py`,
`tests/test_json_governed_shadow_integration.py`.

| Scenario | Required outcome | External provider mutation |
|---|---|---:|
| Unsupported event-log alert class | `unsupported_class` | 0 |
| Alert older than 24 hours | `outside_window` | 0 |
| Exact endpoint offline | `waiting_offline` | 0 |
| Current active EDR detection | `active_detections` | 0 |
| Online, healthy AV/EDR, zero detections | `healthy_observed` | 0 |
| Duplicate exact alert or mismatched device identity | Fail closed | 0 |
| Missing read permission, failed provider envelope or cross-client scope | Fail closed | 0 |
| Interrupted bounded scan and restart | Resume from durable checkpoint; no repeated completed read | 0 |
| Wrong exact playbook fingerprint on restart | Fail closed | 0 |
| Unsupported/caller-supplied approval or health fact | Fail closed | 0 |
| Synthetic exact approval receipt on the legacy-conversion candidate | Propose-only, stop at mutation | 0 |

The five first rows finish their **read-only diagnostic classification**
without action. Tests also verify immutable versioned draft staging in an
isolated SQLite instance creates no active version or execution grant.

## Limits / incomplete migration gates
1. Actual provider/tenant read binding through Jason's existing Central
   Orchestrator remains to be integrated and independently checked in a
   separately isolated preproduction service; synthetic fixtures do not
   constitute live provider readback.
2. This pilot excludes the legacy DRMM workflow's alert resolution, exact
   Autotask note, ticket completion, and 24-hour multi-alert scheduler.
   Accordingly **it is not one of the 19 completed migrations**.
3. Current shared shadow integration intentionally blocks every mutation;
   production policy, approval, side-effect idempotency and provider write
   reconciliation remain the responsibility of existing governed action
   paths and need separate end-to-end tests before any JSON replacement.
4. Production JSON registry remains unchanged; no migration activation,
   legacy retirement, release change, service restart or protected Core
   change is requested or implied.

## Section Goal Closure
**Source-level isolated read-only pilot acceptance: PASS when its new
CI source gate reports success at the exact branch SHA.**

**Actual environment-connected preproduction acceptance: NOT YET PROVEN.**

**Legacy migration reconciled: 0/19 fully accepted.** Retain the existing
legacy implementation and protected PMv4 boundaries unchanged.


## Runtime-service preproduction composition proof (source-only)

The independent opt-in builder at
`implementation/runtime_service/src/jason_runtime/json_playbook_readonly_preprod.py`
now uses the **existing** `SQLitePlaybookRegistry(..., read_only=True)`
to inspect an exact isolated **draft** `drmm_recent_alert_readonly_shadow_pilot@0.1.0`.
It enforces its immutable fingerprint, exact read-only capability set, and
nonactive state. The existing
`jason_runtime.autonomy_shadow_runtime.GovernedAutonomyReadPort` composes
the service principal's authorized Observe request and the Central
Orchestrator; the builder does not create new provider transport, an
alternative runbook registry, a competing Ticket Core scheduler or any
mutation capability.

`implementation/runtime_service/tests/test_json_playbook_readonly_preprod.py`
tests this composition using fake in-memory authority and provider
responses with **ten isolated scenarios**. Client scope, explicit Observe
policy, exact registry fingerprint, refusal to load active versions,
restart/idempotency, and the five supported read-only classifications are
covered. Neither these tests nor the builder connect to the production
Core, a real client endpoint, or a live provider API.

**This establishes test-backed source-level integration readiness for an
isolated preproduction environment, not live provider acceptance.** No
production JSON stage, activation, release, or legacy retirement is implied.


## Repository integration coordination

This component-scoped source PR is independently reviewable from the
19-playbook migration workstream in PR #2611. Both PRs intentionally reference
the same read-only adapter sources while the larger migration remains
unaccepted. Merge the isolated read-only component only after its own
required checks pass and its base is current; reconcile PR #2611 against
the resulting protected `main` revision to remove overlap. A source merge
does not deploy the component or activate JSON playbooks.
