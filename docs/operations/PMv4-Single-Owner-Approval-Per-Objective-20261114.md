# PMv4 — one authenticated Owner decision per bounded objective

**Date:** 2026-11-14

**State:** SOURCE-ONLY design, conformance adapter and governance-amendment candidate; **not** live Owner authority, not an installed approval/routing workflow.

**Owner direction:** One approval for an operational task, not repeated approval challenges for each already-bounded internal stage.

## Observed cause of approval fatigue

Stage A0 required separate Owner Entra device-code challenges and signed exact-action approvals for (1) six-file root trust, (2) thirteen-file immutable sparse source staging and (3) same-image MCP issuer activation. All three were separately verified and consumed. They shared the same protected source SHA, unchanged runtime LKG, freeze, promotion hold, production breaker, and no Ticket Core change. The human performed the same identity/intent ceremony repeatedly because three independently installed native root handlers each accept **only their own one-use exact-action proof**. This is a consequence of current implementation and PMv3 production policy; it does not prove that multiple human votes are intrinsically required for an already reviewed bounded task.

The next Stage A0 native installation still remains a separately governed protected production change under the **currently effective** policy. The earlier proofs cannot be retroactively combined, extended or replayed.

## Desired behavior

One authenticated Owner decision reviews an **immutable, ordered, bounded objective plan**. It may encompass all declared internal phases—engineering, preproduction CI, approved release bootstrap, source staging, bounded component activation, verification, recovery, and rollback—only to the risk, component, target, impact and artifact envelope explicitly displayed. Subsequent phases require **new independently verified machine execution claims, not new human approval prompts**. Safety checks, production locks and rollback are not removed.

Exactly one Approval Service and one canonical release infrastructure are retained. Reuse:

- The existing universal plan/approval service, `PlanGrantLedger`, approval audit and immutable plan receipt.
- Verified Entra/Owner identity binding (ChatGPT authenticated Owner route or licensed Teams route as permitted by governance); a chat statement alone is not a root approval credential.
- The existing protected Release Manager/root signer, native root transition gate, CCC and CI evidence, production freeze/hold, breaker, shared release lock and status receipts.
- Existing PMv3/Workboard durable objective owner, idempotency, recovery, Central Orchestrator step validation and System Registry.

Do **not** introduce a duplicate approval store, alternate root signer, persistent privileged bypass, additional manager, new Teams requirement, or standing release privilege.

## Reviewed objective manifest

The trusted server creates a canonical immutable plan before requesting approval. The Owner-facing review includes:

- `plan_id`, AOT tenant/Owner identity, policy digest, expiry, maximum risk and permitted production impact;
- protected source and exact rollback SHA, pinned freeze/hold and other required root baseline evidence;
- ordered steps, with explicit capability, component, required manifest/release scope digest, artifact hash, expected side effects, downtime/restart boundaries and rollback;
- explicit exclusions (in PMv4 Stage A0: no Ticket Core stop, no provider writes, no production pointer switch, no PMv3 retirement);
- independent acceptance checks and a durable correlation/event reference.

After verified Owner consent, the existing Approval Service persists **one human decision** bound to the plan fingerprint. The native root gate may derive a unique, one-use proof for each *already reviewed* step only after it independently confirms that the plan remains active and that the step is exactly within its signed constraints. It must not accept a caller-chosen step, mutable source plan, generic shell command, spoofed identity or merely a recorded chat approval.

### Mandatory per-step checks — no additional Owner prompt

1. The original identity-bound approval, audit signature, policy, expiry, revocation and exact ordered plan digest remain valid.
2. The next step matches the Owner-reviewed capability, component, release/manifest/artifact, maximum risk, target and impact. It does not reach a different tenant or protected Core.
3. Native root reads its **own** protected authority, source/CI, freeze, hold, breaker, health, transaction lock, and immutable step material; a caller's status fields cannot substitute.
4. Prior step has a verified root receipt. A completed step is not performed twice. A crash, unknown provider outcome, tampered receipt or collision is reconciled or held rather than blindly replayed.
5. Independent CCC/release/security requirements still pass. Root emits a substep audit including parent approval ID, immutable plan digest, exact step digest, verifier, execution/rollback result, and unaffected-service health.
6. If all in-scope checks pass, the existing governed executor continues without asking the Owner to repeat the same consent.

New Owner consent is appropriate only for an impact/capability/tenant/risk outside the reviewed plan, an actual new independently required production class, an expired/revoked grant, or material drift. Revisions that can be proven inside a **formally approved bounded source-change envelope** do not require repeated decisions solely because Git commit hashes advance; the deployed artifact is always independently verified against its exact final SHA. In the current PMv3 policy, final exact SHA approval remains required until this specific amendment is lawfully activated.

## Existing source-only conformance adapter

`implementation/orchestrator/pmv4_objective_scope.py` reuses the **existing** `PlanGrantLedger.require_grant()` gate for each distinct ordered step. An immutable owner-reviewed manifest fingerprint binds each step's source, scope, artifact, protection hashes and risk. Changing its order, adding a step, changing an artifact, changing the protected source or crossing a policy/tenant boundary causes denial. It does **not** mint Owner proofs, record human votes, modify root policy, execute a release, or bypass anything.

The existing continuation and native execution layers must perform authoritative root/machine checks. The current adapter accepts observed facts from a **trusted** host projection; passing facts from a user/LLM would be unsafe and is explicitly out of contract. No service calls this adapter in production.

A separate, strictly dormant **cryptographic binding primitive**
`implementation/kernel/pmv4_plan_child_proof.py` reuses the **existing**
Ed25519 Owner release signer/key format through `signed_owner_release.py`
without modifying the legacy v1 release-proof verifier. Its new distinct
schema `2.0` binds one child claim to the original authenticated plan
decision digest, parent approval ID, ordered action index and name, Owner
identity, current policy, source/rollback/freeze/hold, scope/artifact hashes
and both the 15-minute step TTL and parent plan expiry. It explicitly says
`prior_authenticated_owner_plan` and must **never** masquerade as a new
live Entra OAuth bearer. The legacy root proof verifier rejects this new
schema, so it cannot authorize existing production root releases. Signature
verification, matching trusted expected fields and consumption are separate:
an affirmative cryptographic check does **not** issue authority or skip
native root receipt verification.

**Necessary integration still missing:** Existing authenticated universal
plan continuation must verify the real one-human-decision audit and call
the conformance gate before issuing a child proof; the independently
trusted native root consumer must verify the signed parent evidence,
current plan revocation/expiry and exact child claim before any mutation.
That integration is not in the live runtime or production root handlers.
Ephemeral-key tests are evidence of source cryptography, not live Owner
identity or protected host acceptance.

### Source-only one-consent, four-step acceptance (November 14)

The existing owner plan grant SQLite class now contains an **opt-in, atomic**
`record_authenticated_owner_objective()` extension; it reuses that exact
database, not a second authority system. The existing grant and full signed
parent proof commit in **one SQLite transaction**. A failed proof storage
transaction leaves no orphan human grant. Retrying the same still-valid
Owner plan after service restart returns the **same signed receipt without
presenting a second human consent**. Changed Owner identity, expired
authorization, or revoked grant fails closed.

`issue_authenticated_owner_objective()` in the **same already introduced
cryptographic module** accepts a real independently signed/verified Entra
OAuth bearer through the existing verifier contract, checks exact AOT
tenant, audience, issuer, allowed Owner object ID, expiry and token age,
checks protected source, and presents the **entire canonical plan and
fingerprint to one exact Owner consent callback**. It signs the parent
receipt with the existing Ed25519 owner signer interface, not a new key,
and records it in the existing plan ledger. It cannot be reached from the
running production MCP or root service.

`issue_proved_objective_step()` and `verify_proved_objective_step()`
recheck the original stored Owner decision, exact protected release
baseline, scope/manifest, current grant/revocation and the signed parent
at **every** step, then bind each one-use child proof to the same
authenticated parent decision and full action index. These are pure
read-only/signing adapters, **not execution** and not a root permit.

The nonproduction end-to-end test uses a real ephemeral RSA-signed OAuth
JWT and an independent RS256 verifier, a fresh ephemeral Ed25519 service
key, disposable SQLite and four Stage A0 example actions. It verifies
one human consent -> one durable grant -> four unique signed proofs, with
no second consent on retry; rejects forged/expired/wrong-tenant tokens,
altered scope, tampered signatures, revoked plans and consumed steps.
The source-only bridge now requires an **exact sequential set of already
verified prior steps**, and both issuance and root-style verification reject
skipping an intermediate stage. Only the **existing native root journal**
may supply these prior-step completion facts in a future production adapter;
this pure source predicate never treats a caller-supplied completion list
as privileged evidence.

An additional source-only Stage A0 adapter
`tools/pmv4_stage_a_bounded_plan_preflight.py` reuses the **existing**
`pmv4_stage_a_packet` source/rollback/scope hashing and
`pmv4_stage_a_admission.exact_stage_a_manifest()`; it checks CI, root
health, protected freeze/hold, signed parent/child, current grant and
sequential prior native-journal receipts before returning **read-only
preflight facts**. Its `production=True` mode **always rejects**:
`STAGE_A_BOUNDED_PLAN_ROOT_POLICY_NOT_DEPLOYED`. The existing v1
native root worker remains unchanged. Negative tests cover changed
candidate, CI, manifest, root health, ticket/runtime continuity,
freeze/hold, skipped step, expired consent and replay. No shadow or
real root transaction has been claimed by this test.
This is stronger test coverage than the earlier unsigned synthetic
decision fixture, but still no live Microsoft token/provider or
independent privileged root consumer. **Formal PMv3 amendment and a
governed production activation remain mandatory.**

## Proposed amendment and acceptance

**Formal governance change required before production adoption:** Modify PMv3 exact-action Owner authorization to allow **one verified, short-lived bounded-objective Owner plan** to derive separate root-authorized one-use *substep* claims. Preserve the exact immutable final SHA, root readback, production freeze, high-risk control and rollback requirements. Retain the special approval class for actions not covered by that plan. Owner authentication may occur in an authenticated ChatGPT/Entra session; Teams approval is not required.

Minimum acceptance before activating the feature:

1. Two AOT test principals, verified role/tenant, one real Owner Entra consent, one immutable decision covering at least four ordered synthetic Stage A0 steps, **zero additional human prompts**.
2. Independent root-ledger substep consumption, unique one-use IDs and exact material checks. Deny duplicate/replay/concurrent step, invalid signed proof, wrong actor/tenant/role, policy drift, altered source/scope/rollback, new Core writes, expired or revoked approval.
3. A failure between source staging, issuer activation and native installation leaves protected Ticket Core running, the guarded freeze and hold intact, and supports idempotent restart/recovery with **no second Owner vote** while the original plan remains valid. Indeterminate state never blindly replays.
4. Production activation is one **separately authorized** code/policy release; no self-activation by a source merge. Pilot demonstrates one genuine Owner consent and end-to-end independent post-release acceptance with exact rollback and no extra auth requests.

**Current operational rule:** This document cannot authorize the next native PMv4 Stage A0 production installation, nor can a generic chat approval supersede existing protected root policy. Finish engineering and isolated acceptance before presenting the Owner one consolidated approval package for future releases rather than repeating fragmented challenges.


## Formal PMv3 amendment text — DRAFT, not yet adopted

**Proposed successor to Part IV, Section 8 (Exact-Revision Approval)**

> For a bounded objective explicitly reviewed by an authenticated authorized
> Owner, one immutable, expiring, non-transferable approval may cover all
> constituent phases of that objective, including scoped development,
> integration, testing, production publication and operational verification.
> The trusted Release Manager shall independently bind every production
> transition to its exact immutable source revision, complete effect scope,
> reviewed dependency/risk ceiling, immutable artifact digest and verified
> rollback revision. The human approval need not be repeated when a
> deterministic trusted review proves that the exact current change remains
> within the approved objective and has passed the required independent
> release evidence. New human approval is required if target, risk,
> capability, tenant, production impact, protected Core change or materially
> reviewed source/effect boundary expands beyond the original grant, or
> the grant is revoked, expired or independently invalidated. No change
> to production freeze, root signer controls, provider authorization,
> release locks, rollback assurance or security gates is implied.

**Proposed successor to Part IV, Section 9 (Approval Channel)**

> One decision must be captured by an approved authenticated Owner channel,
> with independently verified Entra Owner identity, reviewed complete plan
> fingerprint, validity window, exact scope and immutable audit. ChatGPT can
> be the presentation surface when the server independently verifies the
> Owner's Entra identity and records a cryptographically verifiable exact
> decision. Microsoft Teams approval is not mandatory. The canonical
> existing Approval Service persists the one human decision; the existing
> root release signer may derive one-use exact substep claims from it only
> through approved and independently validated native release gates.
> Revocation, expiry, changes of authority or out-of-scope changes fail
> closed. Conversational assent, an unsigned status, a fabricated Entra
> claim, or a reusable Owner token do not count as identity-verified
> approval.

**Proposed successor to Part IV, Section 10 (Production Freeze)**

> A bounded objective approval does not unfreeze production globally.
> Each independently attested, in-scope production step receives only its
> exact single-transaction exception and must restore the original freeze
> and automatic promotion hold byte-identically. Any out-of-scope step
> remains prohibited. Nothing authorizes unattended disruptive
> operations absent the specifically reviewed impact and independent
> safety requirements.

**Effective-date and release condition:** These proposed paragraphs have
no effect until an authenticated Owner expressly adopts the exact text as
a formal governance amendment, the change is reviewed and merged through
the protected release process, and the associated bounded-plan root
consumer is independently tested and deployed. Existing PMv3 Section 8/9/10
and installed v1 Owner exact-release signer remain binding until then.

**Transition strategy:** The current Stage A0 release is still pinned to
`7b42ce983896711525de4c7955bf9fc43ac003d0`. Do not merge or promote
this draft merely to accelerate that release. After native Stage A0 is
successfully completed and its root audit reviewed, integrate this
feature through the ordinary exact-SHA governed release, initially
disabled/shadowed; run a four-step independent root readback canary and
negative-path acceptance; only then switch release approval consumer
to the one-plan policy under an Owner-reviewed separate one-time release
authorization. If any validation fails, return to the v1 exact-action
consumer, preserve signed audit, and restore the protected freeze/hold.
