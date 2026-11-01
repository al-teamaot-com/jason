# Production Manager — Phase 1: Reliability-First Controlled Releases

**Owner direction:** 2026-10-27. **Priority:** P0. **Production deployment freeze:** ACTIVE until separately and explicitly lifted for a bounded acceptance transaction.  
**Authority:** Existing Jason Change Integration & Release Standard, protected GitHub main, canonical CCC, Release Manager, root-owned Production Control.  
**Supersedes nothing:** This is an acceptance checklist and sequencing rule. It creates no new deployment authority or independent controller.

## Section Goal

Make Jason's **existing foundational functions reliable** before expanding automated engineering. A change must not overwrite unfinished work, silently supersede another merged change, or turn a previously working read function into a broken one.

**Phase 1 does not include autonomous development.** Owner/technician-approved fixes may be prepared and code-reviewed independently, but production promotion requires an exact-version governed manual approval and the checks below. Do not mistake creating/merging a PR for production acceptance. A standing release freeze overrides all routine approvals.

## Required release transaction

1. **Record the baseline.** Capture exact running runtime, MCP, immutable host, Release Manager controller and root-managed systemd revisions; image IDs; declared timers; protected last-known-good and circuit-breaker readback; fresh drift/CCC and zero failed required units. Keep an independently verifiable rollback target.
2. **Protect parallel work.** Compare candidate changes against all relevant open PRs and implementation-sensitive overlapping paths. Resolve overlaps in protected GitHub reviews. Do not reset, clean, prune, force-remove, or replace an active/dirty Git worktree or a teammate's branch. An unmerged workstream stays in its own worktree.
3. **Require current protected source.** Exact candidate SHA must equal fresh protected-main HEAD immediately before promotion and descend from verified live production. Stale prepared/approved candidates are rejected and must be reprepared and revalidated. Required protected checks must pass. Approval is **exact SHA**, not a reusable permission for newer code.
4. **Establish safe resources.** Assert measured root/archive disk and inode headroom sufficient for build, immutable images, rollback, and logging. A low-capacity or unhealthy host blocks build and promotion. Never clear pressure by truncating audit logs, live SQLite/WAL, rollback images, or active worktrees.
5. **Independent preproduction.** Build immutable runtime/MCP images from the exact SHA with provider mutations disabled and isolated writable state. Verify controller self-upgrade staging, root-managed service/timer delta, manifest identity, CCC/checker compatibility and rollback artifacts. Failure must not touch production.
6. **Foundational read canary — before promotion.** Using **authorized, read-only** Jason MCP identity, freeze a non-sensitive ticket creation time window (both `created_after` and `created_before`). Run `service.ticket.count`; retrieve **all** matching tickets through `service.ticket.search` pagination, checking no duplicate IDs, complete records, stable bounded count and all request statuses; `service.ticket.read` one known authorized ticket and confirm exact ID/number. Inspect provider, error codes, correlation IDs, warnings and pagination metadata. Also verify core RMM/Teams functions actually affected by the patch, rather than only container health. Do not publish raw client ticket data in a release artifact. A denied/error/partial read is **FAIL**, not success.
   The source-level verifier `implementation/orchestrator/foundational_ticket_read_acceptance.py` now executes those **three read capabilities across all required search pages** using an injected, *already-authorized* JKD-001/Central Orchestrator read port and returns only non-sensitive count/page/exact-read evidence. A zero-count, missing page, wrong provider, denied read, invalid window or post-release revision mismatch is a failure. **This verifier is not an access grant or a release-approval authority.** Do not run it under the CCC service identity for positive customer ticket reads: existing source requester authorization correctly denies that use. Until an authenticated owner/technician read port and verifiable evidence handoff are wired into the native release controller, a release must not be marked **FOUNDATIONAL FUNCTIONAL ACCEPTANCE PASS** just because its CCC or container checks are green. The operator must obtain real authorized live read evidence for the exact candidate before and after deployment; synthetic CI fixtures only prove that the validator rejects incomplete data.
7. **Governed promotion.** Only when the freeze is separately lifted for an explicitly identified transaction: obtain an authenticated owner decision for the exact candidate and material changes, acquire the **exclusive production lock**, refresh protected main/production baseline/circuit evidence and recheck the exact source at the last pre-mutation boundary. Never promote via direct Docker, shell replacements, user worktrees, or an alternate deployment lane.
8. **Verification or rollback.** Verify new runtime/MCP/host/controller/image/unit identities, health and fresh independent CCC/drift. Repeat the same authorized foundational ticket canary **after promotion** with a fixed window and exact-ticket read; run feature-specific checks. If any mandatory gate fails, initiate native known-good rollback, verify restored identities and foundational read behavior, keep the circuit breaker OPEN if unresolved, and report exact evidence. A healthy HTTP status alone is not acceptance.
9. **Closeout and observability.** Persist immutable source IDs, read-canary summary (never customer content), pre/post results, approvals, independent manifests, rollback readiness, deployment and functional verification, any warning and follow-up. Mark production acceptance only with all required evidence and zero unresolved critical defect.

### Root-governed cleanup for pre-manifest historical rollbacks

The existing immutable host release reconciler is the only authorized unit
cleanup path. If a protected exact LKG predates
`production-desired-state.json`, the root worker compares canonical unit
definitions in that exact immutable release against the currently installed
candidate's reviewed manifest, for both system and user units. Only an
independently verified LKG may use this compatibility mode.

The root helper preflights both scopes before any mutation, requires a
byte-identical installed candidate unit and correct ownership, rejects
untrusted symlinks and bulk removals, and stores a private root-owned
per-request backup before disabling/removing a candidate-only unit. No
unrelated services or customer endpoints may be touched. A failed/uncertain
cleanup must block release verification and keep protected recovery active.
Historical release files are never modified or patched in place.

A green isolated test does **not** prove the live historical rollback.
The complete cleanup, service health, protected policy, old/new controller,
and source-manifest readback remain part of the separately authorized
production acceptance gate.

### Mandatory authenticated Autotask canary for every release (source candidate)

The native release transaction must verify the same genuine AOT-authorized
requester's ticket count, complete bounded pagination and exact ticket read
**before the first production mutation and again after the complete
runtime/MCP/host/controller cutover**. This is mandatory even for a change
unrelated to Autotask, not conditional on changing the read activation profile.
The postflight also requires activated catalog-specific generic reads:
v11/v13 Projects; v13 dynamic ActionTypes. The baseline can be an older
immutable MCP release whose historical single-call BEFORE probe contains
only ticket reads; its preflight must still prove real ticket behavior, and
unobserved generic reads must never be reported as verified. A genuine failure
must block promotion before any mutation or trigger native LKG rollback after
cutover. A test fixture, HTTP status, service-only identity or stale
receipt cannot satisfy either gate.

Both phases use distinct nonce-bound, exact-candidate-sha sessions. The
single MCP canary tool supports both phases; the provider release identity
and permitted read path remain unchanged. Verify that the pre/post created
window digest and SHA-salted authenticated principal digest agree; raw ticket
contents, ticket IDs and human identity do not belong in release receipts.
Only a verified preflight from the same exact candidate may be replaced by
the postflight intent. Unknown profile, missing consent, absent authenticated
AOT operator, expired/mismatched proof or no authorized provider result
remains **BLOCKED**, never silently downgraded to a synthetic canary.

**Operational limitation:** The pre/post acceptance requires a genuine
authenticated requester using Jason's ordinary read capability. This source
change does not grant unattended service-provider rights or invent a
technician identity. Preproduction tests can prove control flow and negative
cases but cannot substitute for a later owner-authorized live acceptance.

## Phase-1 operating constraints

- The existing **incident hold** continues to block unattended promotion; do not remove it during the freeze.
- **Timer/release serialization:** The separate approval-only Teams timer must acquire the *same* exclusive production transaction lock nonblockingly for the full approval-only cycle. If an authorized promotion is holding it, exit 0 with `PRODUCTION_TRANSITION_IN_PROGRESS` without reading the mismatched intermediate runtime/LKG state, consuming owner decisions, or issuing cards. A mismatched LKG **without** an active transaction remains a genuine fail-closed incident. The timer cannot promote releases and must not disable the root drift/circuit breaker. Verify this through a disposable real-systemd timer overlap test and a later normal scheduled cycle.
- The distinct `production-deployment-freeze` marker enforces an Owner-ordered **all-promotion freeze** in both the manual and unattended Release Manager paths. It is separate from the existing incident hold used for the ordinary manual-only schedule. The shared controller rejects any existing marker (even a directory or dangling symlink) before taking a production lock, again under the lock and at the last pre-mutation boundary. It does **not** block read-only work, preproduction preparation or independently governed emergency baseline recovery. Never treat a source merge as activation of this new gate; the installed controller must be independently verified. Removal of this marker requires a new, explicit, exact-release Owner release-unfreeze decision; do not erase it as a generic self-heal action.
- Do not restart running user-facing production or intentionally inject a live failure to certify rollback. Full-stack fault injection belongs in a disposable independent systemd+Docker lab, with no production credentials/network/client data.
- One change/release transaction at a time. Keep unrelated development unmodified. A blocked release does **not** excuse skipping tests or editing production directly.
- Release Manager's own controller changes are production-control-core and require staged N→N+1 evidence; no live controller semantics changing mid-transaction.
- Continue monitoring existing production services and ticket work; stopping **deployments** does not mean stopping normal customer support.

### Release-specific scheduled-control verification

Production Manager evaluates the required user/system **control timers for the
exact immutable SHA being read**, not against the currently installed
controller's newest timer list. A release with a valid desired-state manifest
uses its own required-unit declarations. A historical pre-manifest release
uses only canonical timer definitions present in that same immutable release.
Malformed or missing immutable evidence is a hard failure.

An extra active control timer belonging to a later release (for example,
`jason-production-drift-watchdog.timer` after rollback to an older baseline)
is **release drift**, not a reason to demand that the historical release
adopt the newer timer. PM must fail verification rather than silently stop,
disable, uninstall or suppress the timer. Only the existing guarded root
host-unit reconciliation may remove candidate-only units; successful cleanup
must be separately evidenced by exact release and health readback. The source
unit tests are not a substitute for that production acceptance.

## Acceptance tests before closing #1078

- An ordinary fix and a concurrent unrelated work-in-progress PR are preserved; stale manual and stale automatic candidates are rejected before production mutation. Verify dirty/untracked files still exist with identical content after an isolated acceptance cycle.
- Full-stack disposable-lab scenarios from #1581: partial runtime/MCP swap, candidate-only host-unit delta, failed root rollback, and successful authorized recovery, each with exact before/after evidence and a fail-closed breaker.
- One separately Owner-authorized governed production acceptance release, not a synthetic PASS, proves exact runtime/MCP/immutable host/controller alignment, root-managed units, independent CCC/drift, and a genuine **successful Autotask ticket read/count/pagination canary before and after**.
- No fallback to generic `healthz=200` as proof of ticket-search correctness, and no user or technician should have to challenge Jason to continue a incomplete investigation.
- No automatic-development claims until the above foundation is production-accepted.

**Progress semantics:** SOURCE MERGED ≠ PREPRODUCTION PASS ≠ PRODUCTION PROMOTED ≠ FUNCTIONAL ACCEPTED. Report each separately, including the specific evidence gap when a gate blocks.

### One-call authenticated read verification for v11 promotion

The merged v11 native Production Manager acceptance gate requires post-deploy
connected MCP read proofs from the **same authenticated AOT human** for a
bounded count, complete 50-row cursor pagination, exact ticket ID and a
governed Projects generic search. The source-integrated
`verify_release_ticket_read_canary` MCP tool now performs these four
operations in **one authorized read-only invocation** when `phase=after`
and the active immutable profile is v11. The operator supplies an exact
candidate SHA and a bounded, known-nonempty ticket creation window and
uses `page_size=50`. The MCP tool neither grants source read rights nor
emits release approval; receipt generation occurs only within successful
ordinary `execute_read_capability` requests. A source- or
requester-authorization failure, missing Projects read, incomplete
pagination or wrong revision fails closed.

The independent native Release Manager accepts only metadata-only,
session-bound events witnessed through its own protected canary state;
the MCP tool's summary by itself **cannot** turn a promotion green.
Production remains frozen until the existing exact-SHA Owner exception
and all native release/rollback preconditions pass.
