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
