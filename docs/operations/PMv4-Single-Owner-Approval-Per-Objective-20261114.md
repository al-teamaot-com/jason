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

## November 15 — one human Owner decision now exercises the actual native Stage A0 sandbox transaction

Previously the signed bounded-plan code could only pass pure cryptographic and read-only native preflight checks; it was **not connected to any file-creating transaction**. A narrowly scoped extension to `NativeStageAInstaller.install()` now accepts separately verified *bounded-plan evidence in disposable nonproduction sandbox mode only* and exercises the same exact Stage A0 create/journal/readback/empty-rollback engine used by the older one-proof installer. It preserves the old v1 Owner proof path unchanged. This is **not** a production root policy amendment or permission to execute schema-v2 approvals in production: the native method unconditionally denies schema-v2 evidence when `production=True`, before opening the release lock or writing any files.

A synthetic RSA-signed Entra-format credential, an independently verified **single** human Owner consent, durable existing `PlanGrantLedger` parent receipt, ephemeral Ed25519 parent and ordered child signatures are used to create one disposable Stage A0 native installation. The native journal binds to the original parent approval ID and exact child's cryptographic hash; no additional Owner decision is minted for install, verification or empty-baseline rollback. Repeating the action fails on its existing native journal. Adversarial acceptance denies no/invalid prior step, consumed claim replay, revocation, changed parent/child signature, changed protected hold, broken runtime/MCP health, unavailable CI, caller-controlled executable field and injected legacy test-key override **before any journal or target mutation**.

The new isolated GitHub workflow `pmv4-one-consent-native-sandbox.yml` runs this exact integration in ordinary and disposable UID0 runner environments, with no live host mounts, signer, Entra credential, production release freeze, provider writes or ticket runtime change. The 1-human-decision acceptance verifies a *synthetic* Owner session; it does not represent a new live Entra approval, a deployed root consumer or readiness to spend the Owner's explicitly reserved final production approval.

### Exact outstanding production integration (DO NOT SHORTCUT)

1. The real Owner grant is stored in the existing universal approvals ledger, which may be writable outside the protected root trust boundary. **A root consumer may not treat its unsigned absence-of-revocation or caller-supplied prior-step list as authoritative.** An independently authenticated current grant/revocation readback and native root journal verification are mandatory for each derived step; no plan-controlled shell command or generic root writer.
2. Adopt a governed policy amendment allowing *one authenticated Owner decision for one fully reviewed immutable objective*, with explicit risk/scope/artifact/rollback/revocation envelope; do not claim the dormant source-only proposal is already adopted.
3. Develop, test and publish a separate exact root-owned schema-v2 parent/child consumer and native installer admission, not a mutable checkout import or transformed/fabricated schema-v1 proof. Prove crash/replay/expiry/revocation, root lock and rollback in a full disposable root acceptance and independent CI.
4. Validate the existing full 4-SQLite+backup/restore recovery and closed production breaker, exact 14-file Stage A0 source and protected main CI before any production A0 installation. Native Ticket Core, MCP, freeze/hold and auto-promotion pause remain protected.

**Recorded latest root state (15:10 UTC Nov 15):** Updated V2 full-integrity helper/policy were installed with the earlier Owner authorization; full-integrity systemd service was still running from 14:44:51 UTC and the independent breaker remained OPEN. A0 missing protected source and root closure helper were still absent. Do not restart that health service or repeat a consumed authorization. No additional Owner action is requested by these source-only tests.

### Concurrent source integration review (Nov 15)

PR #2490 independently changes the Stage A0 sparse-source dependency closure and appends CI tests to `.github/workflows/validate.yml`; this PR independently appends one-Owner-decision tests. Exact source-only HEADs `9b5e9c4e8c48d3fc546796c9bcc9bd8f81913133` (#2489) and `617b5af950095dba7052b2b8a46bcdfabbe08331` (#2490) were compared without mutating the branches. `git merge-tree --write-tree` exited 0 and produced combined tree `c559733061c8bc7833b391da6eb674669ad6fd2a`, demonstrating that their CI edits do not conflict. The current overlap gate requires the documented **Integration coordination: #2490** PR body line; a new push is required because GitHub's previous workflow event held the older PR body snapshot. This review authorizes **no** source merge or production transition.


## November 15 — durable prior-step, revocation and interrupted native-receipt recovery (sandbox-only)

Before this change, the initial sandbox native adapter accepted `verified_prior_steps` and `consumed_step_claims` directly from its caller. That is **not sufficient evidence** for a privileged native multi-step release. A new `tools/pmv4_bounded_plan_journal.py` prototype replaces those inputs with a durable, append-only, hash-chained **self-read** of exact parent-approved claims and completed stages. Exact prior-step order, one-use step IDs, parent signed Ed25519 receipt, current operator-side grant/revocation and expiration, expected signatures, source/rollback/freeze/hold/manifest and initial journal enrollment are rechecked before any native Stage A0 file creation. Invalid/revoked/replayed/missing predecessor steps deny. All append writes are file-locked, fsync'd, mode 0600 and stored under a private UID-owned 0700 `/tmp` sandbox for tests **only**. The production root path still rejects plan evidence before acquiring a release lock or writing a release file.

The actual sandbox native Stage A0 installer now obtains verified predecessor and consumed-claim state solely from its `BoundedPlanJournal`; the caller cannot populate those fields. A one-use claim is durably recorded after native source/scope/empty-baseline checks and immediately before native journal `prepared`. After verifying all native objects and appending `verified_installed`, the native code durably commits the completion to the plan journal. If interrupted *after* successful native installation but *before* completion of the plan journal, `reconcile_bounded_plan_completion` allows **no additional Owner decision**: it requires the original immutable native chained journal be at `verified_installed`, every native source/plan/approval/child signature hash match, unchanged native installed file bytes and metadata, and active nonrevoked Owner consent at recovery time before append. Repeating the completed step denies; unfinished, failed, revoked, foreign/tampered native receipts deny. This is not a bypass of rollback checks or a general retry of an already-consumed native installation.

The initial 25 dedicated negative/positive journal/native tests passed. Expanded local suite: **166 PASS, 1 SKIP** across original legacy/native and plan-admission tests, plus root-journal tamper/expiry/revocation/replay and post-native-succeeded/interrupted-plan-receipt reconciliation. The true disposable UID0 GitHub CI acceptance must also pass before treating this as source-verified. Historical three predecessor stages in the test are **synthetic**; the final stage uses the actual isolated native file-creating installer and recovery. No real root production plan journal, root-protected current signed revocation feed or privileged schema-v2 consumer is present. An unsigned/operator-owned universal SQLite grant cannot become production root release authority. Finish that trust integration and governed production-policy amendment separately; retain the user’s one remaining Owner approval for a verified exact objective rather than spending it on a test or code bootstrap.


## November 15 — no raw-operator-DB status at native root admission

The existing universal approval SQLite is mode 0600 but **UID1000-owned**, so a privileged release controller cannot safely treat its direct `revoked=false` read as authoritative. A read-only, independent issuer/consumer prototype in `tools/pmv4_current_grant_attestation.py` now signs a narrow **30-second** current-active-unrevoked assertion, only after verifying the original signed Owner parent, exact action and immutable manifest, pinned Ed25519 signer, and live existing grant/absence of revocation. No additional human Owner prompt occurs; this is a fresh *machine status attestation*, **not a second approval**. It includes original signed parent digest, identity, frozen candidate/rollback/hold/scope/artifact, exact action index and one-plan/nonstanding attributes. The receiver verifies the original Parent signature and independently signed assertion against its pinned key, requires exact scope, current time and 30-second bound, and denies changed/forged/expired/missing grants.

The disposable native Stage A0 sandbox installer now requires this new signed current-status evidence before querying its durable plan journal and creating any source file. The original v1 native Owner proof path and production root path remain unchanged. The stand-alone 20 attestation tests and 15 sandbox native-plan/attestation tests passed; expanded preprod/legacy/security CI still required. **The root consumer of schema-v2 signed plan and attestation remains NOT DEPLOYED**. A future root worker must trust a root-installed signer/verifier and its native monotonic revocation+claim journal, perform fresh root observation immediately before mutation, and deny when it cannot obtain a fresh attestation. Short-lived statements alone do not authorize release, permit direct access to mutable operator SQL, or override current root gates. Owner's one remaining approval remains reserved for the complete exact reviewed objective.


### Final engineering acceptance and native breaker recovery — November 15, 10:44 EST

The expanded source-only encrypted Owner plan, native journal, child-proof, current grant and exact A0 legacy compatibility suite now reports **188 PASSED, 1 SKIPPED**, with standards/doc control PASS. No root schema-v2 consumer deployed. The real previously Owner-approved V2 full four-database integrity and backup/restore proof completed 10:38:43 EST: all four DB integrity results `ok`, backup integrity `ok`, restore integrity `ok`, backup/restored counts match, status PASS, zero provider calls. The independent fast health at 10:41:03 EST and production drift watchdog subsequently reported PASS and no problems. The release breaker remained OPEN after the original recovery process. The **existing native root-governed revalidate operation**, which first independently captures the last-known-good production manifest, was invoked only after validating current full and fast PASS, fresh root drift PASS, protected current LKG, original freeze SHA256 bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f and promotion-hold SHA256 11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0. Root transition service independently revalidated and CLOSED the breaker at **15:43:31 UTC**, exact source `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. No direct protected-state edit, unfreeze, release, restart, root privilege bypass or new Owner prompt occurred.

The Stage A0 one-file missing root source and its new trust helper are still absent, and PR #2489 remains draft. Future single-approval deployment must independently verify the **native root plan consumer and signed current grant status attestor are actually root-pinned**, and must attest a single exact multi-step authorization scope; a successful source-only test or breaker CLOSED does not authorize A0 installation.


## November 15 — distinct rollback binding for heterogeneous exact stages

The remaining PMv4 Stage A0 root bootstrap, source closure and native isolated install all share the protected Stage A0 source candidate, but their **rollback targets are not interchangeable**. Previously `BoundedObjective` had only one global `rollback_sha`; that could not correctly represent an overall one-consent objective. The reviewed `ObjectiveAction` now optionally binds its own exact `rollback_sha` (40 hex characters), included in the immutable canonical Owner-reviewed manifest **only where it overrides the plan default**. The original no-override manifest remains byte-compatible. Root-observed step conformance, signed child proof, and fresh signer-attested current active grant all require the correct **per-step** rollback, not the plan-wide default. Changing the override after consent changes the parent fingerprint and denies. Schema-v2 plan remains source only; this is NOT a way to reinterpret or replay any prior v1 approval.

Negative/positive tests exercised **four differently scoped exact stages under one synthetic Owner decision**, with three separate rollback SHA overrides and native A0 retaining the global empty-baseline rollback; an incorrect global fallback for an overridden stage is rejected before action. Initial focused mixed-rollback suite: **82 passed**. Formal live Owner consent and privileged root release acceptance still required before one-plan production execution; no Owner approval has been requested or consumed by these code changes.


## November 15 — exact three-stage review contract and MCP single-consent ingress

An audited **source-only** `implementation/mcp_service/src/jason_mcp/pmv4_bounded_owner_bridge.py` now binds a verified, current Microsoft Entra owner bearer (verified tenant, subject and signed JWT through existing service) to a full immutable ordered plan; only the precise `approve_exact_one_pmv4_objective` affirmative decision is accepted. The same trusted Ed25519 Owner signer and existing durable PlanGrantLedger are used; the original signed parent and its unchanged grant can be replay-read after an interrupted response **without requesting a second human approval**. Cross-tenant, foreign Owner, nonexact decision, source CI failure, changed plan, revocation or substituted token denies. The source-only bridge unconditionally denies `production=True`, does not register a live MCP action or call any root worker, and never reads or exposes private signing material through user output. The integration test now exercises the real MCP identity-binding *before* the actual native Stage A0 sandbox create/rollback, proving one user-facing Owner decision in this chain rather than only testing disconnected source functions.

The finite `config/pmv4-stage-a0/one-owner-recovery-review-20261115.json` (SHA256 `f5f525e33e4cad46827018e23ea7ae8f72603459dcd740bfbf63f9a176cfa52a`) binds exactly three **previously independently reviewed** root scopes under one proposed Owner plan, all at protected source `7b42ce983896711525de4c7955bf9fc43ac003d0` with current production LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`, freeze SHA256 `bdae4f...` and hold SHA256 `11f0f...`: (1) root source-closure helper bootstrap scope `e5515b...` with archived original plan SHA `25e68e...`, (2) the one missing immutable root source scoped by the exact proposal SHA256 `089f870...` with Git blob SHA256 `ca844f...`, and (3) native Stage A0 create-only install scope `6786ba...` with manifest SHA256 `addba768...`. The global production rollback is LKG; each create-only action has the separately disclosed rollback-to-absence SHA `000...` bound in the immutable parent review fingerprint. No provider, ticket runtime, MCP image, freeze/hold or production current-pointer mutation appears in the reviewed action allowlist. The archived bootstrap and proposal both remain explicitly **NOT AUTHORIZED**; the new review manifest cannot alter that on its own.

`tools/pmv4_stage_a0_one_owner_review.py --check-only` validates the exact JSON SHA, strict source/plan/action identity, pinned Git blob, consent count and no-apply contract. On Jason `--check-only --live-readonly` independently confirmed the actual 13 root-owned immutable existing source files at correct root:root mode 0444, missing one file, root helper/policy absent, native breaker CLOSED and root drift PASS, actual full 4-DB+restore and fast PASS, unchanged live runtime/MCP images, current LKG and frozen protections, and **ZERO approvals/writes**. This is a preliminary unprivileged readback. The independent source package's delegated readback still reports `/etc/jason/pmv4-shadow` **unknown_requires_root_readback** because `/etc/jason` is root 0700. The final privileged stage must therefore verify that exact protected target is empty before any write; no shell workaround, trust bypass, special root exception or premature readiness claim is allowed. No final Owner approval has been consumed.
