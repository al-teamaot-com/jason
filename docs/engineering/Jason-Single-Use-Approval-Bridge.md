# Jason single-use, terminal-free approval bridge — implementation contract

**Status:** isolated engineering specification; not active, not an approval receipt, not deployable by itself  
**Tracking:** #1440  
**Owner direction:** 2026-10-15: full engineering/validation/completion approved; QuickBooks Stage 1 and SharePoint governed reads must not be delayed.

## Problem and success

AOT's owner currently may need to open a terminal and provide a reviewed exact source SHA separately to CCC and Release Manager. The intended normal path is a short, authenticated Teams approval or a similarly verified control-panel decision, **one human decision** producing the correct two governance records without any terminal command. The terminal interface must remain break-glass only.

Do **not** interpret this engineering work authorization as a blanket, enduring exact-SHA promotion approval. Each material candidate remains subject to the currently effective production governance policy until the new route is installed and verified. No approval evidence can be generated from the mere fact this issue is approved.

## Noninterference and sequencing

1. QuickBooks production recovery/stabilization (#1437, #1443) and SharePoint read-only search/read (#1117) retain exclusive priority for production manager admission, critical GitHub checks, release/host locks, and unavoidable owner attention.
2. Build/test this feature in its own branch and disposable sandbox. Do not modify shared active worktrees, QB/SharePoint integration branches, live authority DB, current release queue, or production host state.
3. Do not merge into main or trigger production promotion until QB/SharePoint gates and resource contention are reviewed. No broad CI campaigns while they compete for an active release; keep early tests targeted/offline.
4. Stage the path as contract/tests -> non-mutating Teams roundtrip -> audited exact-release integration -> protected rollout with rollback. Break-glass fallback remains available until the full path is proven.
5. Human updates should report exceptions only, not interrupt routine completion. Nothing in this document is permission for an unrelated provider mutation.

## Reuse instead of rebuilding

Existing authoritative pieces are:
- `docs/architecture/J-102-Governed-Approval-Architecture.md` — provider-neutral approval, Microsoft principal binding, JKD-001, exact intent/execution-plan fingerprints, consumption and recovery.
- `implementation/orchestrator/teams_approval_flow.py` and connector Teams approval adapters — authenticated interaction handling.
- `implementation/orchestrator/approval_continuation.py` and the existing durable consumption ledger — one-time continuation.
- `implementation/mcp_service/src/jason_mcp/release_approval_request.py` — release owner-approval request queue, exact SHA/release validation.
- `tools/record_ccc_material_review.py`, `tools/release_manager_gate.py` and CCC material-review schema — existing root-governed acceptance controls.
- `docs/operations/Teams-Approval-Deployment-and-Recovery.md` — transport and recovery behavior.

**Transport does not grant authority.** Never implement an additional independent "valid PIN means approved" execution route.

## UX / delivery contract

For an exact immutable release eligible for owner review, show:
- short purpose and organization, release ID, full candidate SHA, diff summary and changed critical areas;
- risk class, production target, affected providers, user/client disruption if any;
- CI, preproduction, independent reviewer/CCC preflight, rollback status and corresponding immutable evidence links;
- policy version/digest, issuing time and expiry;
- Approve and Deny (optionally Request Changes), with mandatory reason for sensitive decisions.

The card is no-execution by itself; it sends a decision to the authenticated ingress. Expose a safe mobile-friendly fallback page under existing Entra identity and tenant bindings if Teams is unavailable. A one-time code may be a short-lived, rate-limited *challenge associated with that logged-in identity*, never an identity credential by itself. Never put a reusable bearer approval secret in a clickable URL. All UI content is minimally necessary, sanitized, non-secret and non-authoritative.

## Canonical input and binding

A server-owned approval proposal includes:
- `approval_request_id`, `organization_id`, `client_id` (when applicable), `requester_id`, explicitly allowed Jason principal/role;
- `capability` = exact named release/change or operational action; `operation`, approved risk category, expiration;
- exact `release_id`, `candidate_sha`, changed-file/diff digest, immutable artifact digest(s), versioned policy digest; or exact canonical action intent and verified provider execution-plan fingerprints;
- expected effect, rollback strategy and immutable evidence references;
- nonce commitment/hash, idempotency key, creation status, and auditable correlation reference.

The server, not the Teams payload, resolves approver identity, organization, role, authority class, final target, or risk policy. Canonicalize before approval; any material drift supersedes the request and requires a new approval.

## Server-side state machine

`created -> delivered -> authenticated -> accepted/denied/changes_requested/expired/cancelled/superseded`

Accepted is not yet executed:
1. After signed/verified Teams ingress or full Entra verification, bind Microsoft tenant and object identity to exact Jason identity; fail closed otherwise.
2. Re-load pending immutable proposal and current release/action evidence. Compare candidate SHA, organization/client, policy/diff/plan digest, risk and authority against stored request.
3. Apply provider-neutral approval policy and JKD-001, including extra approver/review gates required by risk. Persist one immutable decision and audit evidence.
4. Under a durable atomic transaction, consume the single-use approval/continuation claim for the exact request/fingerprint. Duplicated/concurrent attempts cannot generate a new authority event.
5. Obtain fresh narrowly scoped runtime authority, then route only through the Central Orchestrator and current root-governed release gate.
6. A verified approved *release decision* may emit BOTH the exact-SHA owner approval and CCC material-review evidence through narrowly permitted, separately authenticated/validated root-controlled consumers. Neither a Teams card receipt nor a generic filesystem write makes CCC PASS; CCC still independently certifies its full matrix.
7. If a process crashes between consumption and provider outcome verification, mark `indeterminate` and use the existing governed recovery procedure. Do not release/reissue the consumed token silently.

## Security implementation requirements

- Cryptographically secure random nonces, hashes/commitments in durable server-controlled storage, no plaintext secrets in audit or Git.
- Atomic compare-and-consume durable across process restarts and concurrent decision delivery; replay protection and idempotent exact-result readback.
- Short configurable TTL and bounded attempts; constant-time secret comparison if code-based; no privileged operation solely on code possession.
- Explicit tenant/organization isolation and exact permitted approver; sign/validate transport, treat Adaptive Card action fields as untrusted.
- Deny, revoke, cancel or supersede prior challenges on review material changes, user/role removal and release reissue.
- Scope-limited privileged CCC/release adapter, no generic root shell, no accepting caller-supplied arbitrary file paths or SHA without source verification.
- No creation/extension of approval privileges by the AI, agent, connector, or token issuer.
- Versioned policy configuration for roles, risk tiers, routing, reminders, TTL, safe standing approvals and response escalation; preserve the separate approval class for materially disruptive/financial/core actions.
- Audit correlation `request -> delivery -> verified principal -> intent -> decision -> authority -> CCC receipt -> release owner approval -> execution/rejection -> post-verification`.

## Non-production acceptance

Tests must prove, at minimum:
1. One real Microsoft-identity-bound Teams decision on an inert fixture produces one immutable approval decision and one consumed continuation; zero shell commands from the approver.
2. Deny/Request Changes produce no approval evidence or continuation.
3. Wrong user/role, foreign organization/tenant, absent verified identity or revoked binding reject.
4. Expired, cancelled, already-used, guessed or concurrent duplicate challenges reject or deterministically return the same prior result without repeating any side effects.
5. Changed SHA, release ID, code diff/policy digest, tenant, material payload, provider target, risk tier and stale request all fail closed.
6. Unavailable audit/authority store, Teams delivery outage, broken CCC root consumer or indeterminate execution never yield a false approval, CCC PASS, or second provider invocation.
7. A valid approved exact candidate produces the two correctly signed/bound owner-review records, *without bypassing* CI, preproduction, independent CCC and release manager gates.
8. Restart/crash/retry and root/least-privilege authorization tests pass; rollback and break-glass operations documented and tested.
9. Existing QB and SharePoint integration/release behavior remains unchanged; release throughput is not reduced due to the approval feature.

## Release acceptance

Separate code readiness from production activation. After targeted and broad regression checks plus isolated pilot pass, record exact source SHA, prepared artifact digests, root permission check, rollback readiness and protected release approval. Promote only when QB and SharePoint work have capacity and no blocked critical release. Verify post-release Teams end-to-end for one harmless request and exact-sha CCC/Release Manager audit, then verify existing governed behavior. Declare completion only after live approval and negative-path evidence, with no terminal required for the normal path.

## Operating modes

- `standalone_test`: non-mutating, isolated fake organization or controlled test principals.
- `shadow`: Teams/card proposals and verified decision evidence, but no CCC/release write; legacy approval authoritative.
- `production_enforced`: single decision yields authoritative exact-bound records under current policy; legacy CLI remains audited break-glass fallback.

Default production mode is unchanged/off until an explicitly approved, verified activation.

## Owner supersession: P0 universal plan approvals (2026-10-15)

This section supersedes earlier priority and release-only wording above. Issue #1440 is now P0 ahead of QB and SharePoint development scheduling, without permission to interrupt unsafe in-flight operations or bypass existing protected release checks. Development and tests should proceed on isolated branches; production gates remain enforced until the replacement passes acceptance.

The deliverable is a **universal, multi-user approval service** shared by release/CCC, QuickBooks, Autotask procurement, Datto RMM, and playbooks. No personal principal, chat, email, or role is hardcoded. Route by resolved Entra identity and configurable organization/tenant roles. Support delegated approvers and fallback escalation.

A single identity-verified approval of a specific bounded plan covers all in-scope phases, including repair iterations, CI, release preparation, production deployment explicitly within the reviewed impact, and verification. Distinguish the one-use *approval response* from the durable *plan authorization*. At each execution gate, deterministically attest that the current action and updated source/artifact are still within the plan, authorized risk ceiling, tenant, effect, policy, and required independent review evidence. Hash changes by themselves must not create redundant owner approval prompts; changed semantics exceeding scope fail closed and require one amended approval covering the revised plan. Never blindly copy approval to an arbitrary SHA.

Acceptance must include two requesters, two authorized approvers, wrong-role and cross-tenant rejection, replay and concurrency, expiration, plan/scope drift, unattended completion without repeat prompts, proper audit, and actual mobile Teams approve/deny with post-execution readback. Current feature work approval does not itself grant a live production release or provider mutation.


## Verified runtime integration repair (2026-10-16)

The runtime now composes the existing universal approval service through a concrete
adapter when `JASON_UNIVERSAL_APPROVAL_MODE=enforced`; `off` preserves legacy behavior.
The adapter independently verifies the original Ed25519-signed Teams gateway envelope
under ADR-009, preserves `botframework-authenticated` assurance (it does not invent
an MFA or OAuth assertion), and rebinds the Microsoft tenant/object to live Jason
identity, role, and exact capability authority. Unsigned or changed callback fields
cannot become approval evidence.

`JASON_UNIVERSAL_APPROVAL_DB` identifies the private SQLite plan/receipt/progress
store. `JASON_UNIVERSAL_APPROVAL_POLICY` identifies the separately managed, versioned
policy file. Enabling the service creates no users, roles, grants, or production
permissions. A policy is explicit per organization: role members, capability-to-role
routing, disabled principals, maximum risk, production permission, retention consent,
and a bounded lifetime. An unknown organization/capability or unavailable recipient
fails closed. Policy digest changes invalidate pending plans. The request issuer pins
registered capability versions, actual registered risk, exact target parameters, and
every ordered step in the immutable plan fingerprint. Credential-bearing request
material is rejected instead of copied into a card, database, or log.

Normal conversation requests which actually require approval are delivered through
this composed service and the existing Teams gateway sender. Already-authorized reads
retain their standing authority and do not create a redundant approval card. The
human sees the exact steps, target parameters, highest risk, production indication,
expiry, and fingerprint before deciding. The card never supplies those facts back as
authority. Failed or partial delivery is recorded and never reported as success.

Approval consumption and the decision receipt commit atomically under a SQLite write
lock; competing approve/deny clicks cannot both win. The receipt includes the hash
of the verified signed transport material. Append-only audit records bind that hash
to both authentication and the resolved human actor before accepting the decision.
The old premature `approval.orchestrator.resumed` event was removed: approval is not
execution. The actual continuation emits execution evidence only when invoked.

The existing isolated runtime maintenance process is the persistent plan owner.
HTTP callbacks record approval and return promptly; maintenance continues the plan
independently of the ChatGPT session. A restarted worker reloads immutable material,
checks the original decision/audit chain and current role/authority, and obtains fresh
JKD-001 execution contexts for each exact step. Child step approval records derive
from the same verified bounded-plan grant, not a new human prompt. Completed steps
are not repeated. A crash after atomic decision but before grant publication can
recover from the persisted authenticated receipt. An uncertain provider outcome
remains `indeterminate` with its original consumption claim; it is never blindly
replayed. Source/release changes still require the specialized CCC and Release
Manager conformance checks; this generic adapter does not grant arbitrary new SHAs.

Synthetic integration tests use real Ed25519 signatures, real durable identity,
approval, plan, receipt, and audit stores, real JKD-001 reauthorization and the real
continuation; only the final provider-execution boundary is substituted. Tests cover
two requesters/two approvers, denial, cross-organization identity, revoked roles,
forged callback fields, replay, concurrent consumption, changed policy/material,
normal request issuance, delivery failure, two-step unattended execution, restarts,
and uncertain outcomes. These are NOT live Microsoft desktop/mobile acceptance.
Production activation remains off until a governed deployment and actual Teams
multi-user/mobile acceptance prove the complete provider path.


### Concrete gateway, HTTP and execution-ledger compatibility

The card renderer previously embedded `organization_id` in Action.Submit while the
actual Teams gateway rejects such caller-supplied authority. Approval actions now
carry only `approval_id` and `decision`; the gateway restriction is unchanged. Its
pure parser is shared by runtime and cross-language tests which feed the actual
Python-rendered action data into Node. The gateway image explicitly packages that
module. A recorded queued plan now returns HTTP 202, renders an accurate queued
acknowledgement, and finalizes the gateway's human-decision record without claiming
that provider execution has completed.

The persistent runner also reserves each exact derived step in the existing
`SQLiteGovernedExecutionLedger`. A formal JKD approval alone is not sufficient for
Central Orchestrator execution. Each reservation binds the parent human approval,
immutable plan fingerprint, exact intent and stable idempotency key; normal
resolution, fresh context validation, provider-plan binding, consumption and result
recording remain enforced. Integration tests execute through real JKD context
validation, capability/provider resolution, the Central Orchestrator and its ledger;
only the external provider transport is synthetic. An already completed canonical
result can be recovered after a small plan-receipt crash without another invocation.

Restart recovery re-verifies the original archived Ed25519 decision evidence, not
merely a self-described digest or a status label. The archive is private, bounded,
immutable and contains no bearer token. Both its digest and resolved actor must
match the original authenticated audit chain and atomic decision receipt. Missing
or tampered evidence fails closed before execution.

Terminal state reporting uses the existing Teams proactive transport and fixed
non-actionable text to the active original requester and actual approver only. It
sends no provider result content. A per-recipient durable send claim prevents
repeated notifications across restarts. Unknown delivery is visible as
`indeterminate`; notification failure never rewrites an execution result. This
maintenance runs alongside existing runtime maintenance, not in a new daemon.


### Validation checkpoint

The combined local runtime, approval, identity, request-factory, replay, immutable
plan and connector regression suite passed 927 tests before the queued-HTTP case
was added; the subsequent targeted universal runtime suite passed 45 cases. The
actual Central Orchestrator integration exercises provider resolution, fresh JKD
contexts, exact concrete-plan binding and canonical completed-result recovery.
Node bridge and gateway suites passed 43 tests. These counts describe specific
local runs, not current-head GitHub CI or production acceptance; future changes
must rerun the protected suites.


### Backward-compatible gateway activation boundary

The deployed gateway accepts `status=completed` as a completed interaction, so the
new callback preserves that established envelope while adding
`approval_status=approved`, `plan_status=queued`, and `executed=false`. Its HTTP
status is 202 and its text explicitly says the plan is queued. That is not a claim
of provider completion. This avoids requiring a simultaneous gateway replacement
merely to acknowledge a saved decision. The current live gateway parser and
completion branch were read directly and verified to support this contract. The
additional gateway token-field hardening is a separately tested source change;
activation does not rely on it because the runtime rejects all universal-plan
selection/token fields independently.


### Preproduction execution isolation

The canonical Release Manager's cloned preproduction environment explicitly sets
`JASON_UNIVERSAL_APPROVAL_MODE=off` and
`JASON_UNIVERSAL_APPROVAL_WORKER_ENABLED=false`, and verifies both values. This
prevents copied approved plans from executing when live writable state is cloned
for candidate testing. Runtime settings read the explicit worker flag; production
activation must not be inferred from the presence of a cloned receipt database.

### Callback and recovery-worker publication races

The human decision is committed before its HTTP acknowledgement finishes. The
existing maintenance worker may therefore publish the exact same plan grant or
finish the plan before that acknowledgement returns. Two deterministic tests
reproduced the former unique-constraint error and the latter completed-to-queued
state regression using the real signed approval flow and durable repositories.

Publication now reconciles only an exactly matching, non-revoked stored decision,
including its complete scope, actor, fingerprint and decision time. The append-once
ledger API remains strict, a fresh callback cannot reuse a published decision, and
atomic pending-decision consumption still rejects replayed or concurrent votes.
A late approval acknowledgement cannot overwrite running, terminal, uncertain or
security-blocked execution progress. A prior partial-delivery block remains
resumable after a valid authenticated approval, without clearing execution blocks.
These are in-source regression proofs, not live Teams or production acceptance.

Validation of this handoff repair: both new race regressions failed on the prior
candidate and passed after the repair. The combined runtime, approval, signed
Teams ingress, replay, persistence and release-host suite then passed 1,029 tests.
For host-side tests the component-approval registry path was redirected to a fresh
temporary test directory; otherwise seven unrelated component-scope tests read the
host's real approval registry and report extra components. No live registry was
modified and no synthetic result is represented as a production approval.
