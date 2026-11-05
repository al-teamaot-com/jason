# PMv3.1: consumed one-release unfreeze replacement — issue #2339

**State:** isolated design and red/green safety regression; not authorized for production. Production freeze, engineering Owner pause, automatic-promotion hold and existing consumed approval evidence must not be touched.

## Reproduced failure

Candidate `54f4d2cdc048d8058393d7ee43efd5303042d646` passed preproduction, but the installed N controller failed before mutation on the native deployment-contract checksum for N+1. The one-release exception was restored and marked consumed, with production still at rollback `a8925098f49df7ac4a49a41a9d56bc7dfb745520`. An independent new Owner instruction for the exact candidate/scope/rollback then reached `owner_unfreeze_release`, which rejected the existing fixed-name consumed receipt. The current behavior is fail-closed, but provides no safe renewed execution path.

## Required reusable correction

1. Every release unfreeze must be a distinct *authenticated authorization transaction* with an immutable decision ID and independent evidence (not a locally generated retry nonce or an unverified chat/shell flag). Prefer the existing signed Teams decision consumer and Owner binding.
2. Bind each new decision to the exact candidate SHA, full reviewed scope SHA256, verified rollback, release identity, Owner identity, timestamp/TTL, pre-mutation terminal state and freeze digest. Record the exact prior consumed authorization/transaction lineage.
3. Before allowing a replacement, prove the prior attempt failed **before any production mutation** using protected release state, production-control manifest, runtime/MCP/host alignment, and matching freeze hashes. Never infer this from the absence of a success notification alone.
4. Preserve prior source and transaction receipts unchanged. Store every replacement under its own immutable ID, select it by an exact recorded binding under the release lock, and reject replay, ambiguous active attempts, invalid signature, wrong SHA/scope/rollback, expired decision, cross-identity approval, or changed source.
5. Continue all standard production gates, lock, health/CCC evidence, preproduction contract pinning, rollback, and byte-exact freeze restoration. Do not admit a new attempt solely because someone can invoke a local CLI.
6. Test N-controller/N+1 source-bound deployment-contract compatibility before admitting production, so a previously attested candidate cannot fail solely because the installed controller evaluates a different set of contract keys.
7. Integrate via isolated engineering tests and native PMv3 release admission. A changed source revision needs a new exact-SHA production candidate and separate release authorization. Do not try to deploy the old reviewed scope hash after adding this fix.

## Required acceptance tests

- Prior one-shot attempt returns `production_eligible`, freeze restored byte-for-byte, no provider or runtime mutation; prior consumed receipts remain byte-identical.
- New, authenticated, exact-bound distinct approval can authorize exactly one fresh transaction and then cannot replay.
- Expired, forged, foreign identity, mismatched, ambiguous or reused approvals fail before the global freeze changes.
- Pre-mutation failure, post-mutation rollback, crash-recovery, and concurrent attempts retain immutable histories and correct Last Known Good.
- Regression tests exercise both old N and reviewed N+1 controller contract keys, no unsupported developer paths, and no new Autotask permissions.
- Production acceptance for the technician-authority feature uses existing AOT Autotask Resources (including Lindsey and Adam where eligible), native impersonation/permissions, exact approval, `noteType=3`, `publish=2`, independent note readback, and confirmed absence of client notifications.

The current regression test records safe fail-closed behavior but **does not** implement the signed replacement approval producer/consumer or authorize production deployment.

## Isolated predecessor attestation implemented

`attest_consumed_pre_mutation_unfreeze_for_replacement` is **read-only**. It checks both immutable predecessor receipts, production-eligible release state without recorded production mutation, exact SHA/scope/rollback, byte-identical freeze digests, non-standing authority flags and live production alignment. It returns digest-bound lineage for a *future* independent signed Teams approval consumer. It neither accepts an approval nor creates a replacement receipt. On 2026-11-05, this attestation was evaluated read-only against the real consumed `release-54f4d2cdc048d805` and returned PASS; no mutation or freeze change occurred.

Do not wire this helper directly to a plain CLI `--retry` switch. A second signed Owner authorization and a unique non-replayed native release transaction identity are still required.

## Implemented isolated engineering candidate — 2026-11-05

The source-only branch now implements an opt-in signed Teams replacement-unfreeze path across the mobile card issuer, signed callback, independent host evidence consumer, Release Manager admission, distinct source/transaction receipt identities, freeze restoration, and interrupted-transaction recovery. A consumed predecessor is attested read-only against original receipts, source/release/rollback identity, and live alignment. A fresh authenticated Owner approval remains required and is recorded with immutable lineage; this is not a shell retry flag or standing production authority. A second approved card cannot replay the old grant. No live approval was published, and no production mutation occurred.

The following are verified with isolated fixtures: a prior consumed authorization cannot be reused, a signed replacement has its own request subject and exact prior fingerprints, the host consumer accepts only the signed replacement purpose, normal completion restores the freeze, and crash recovery restores the freeze and consumes the new grant while leaving both original receipts byte-identical. The new read-only offer selector was also evaluated against the actual release `release-54f4d2cdc048d805` and selected `replacement_unfreeze_only` without recording an approval or changing runtime state.

**Not yet production accepted:** all required GitHub checks and independent governance review, native integration/admission under the existing engineering Owner pause, a new immutable release candidate with exact scope and rollback, a separately authorized exact-SHA production release, and existing-account technician/provider acceptance. Do not reuse the earlier SHA `54f4d2...` or its original approved scope digest after this source fix is merged.

## Reviewed concurrent overlap

- PR #2279 modifies consumer handling of a superseded signed Teams release approval and adds a protected-main comparison in the host approval-only path. This candidate retains its protected-main check for replacement-only decisions and does not alter the historical release approval flow; reconciliation must preserve #2279's separate superseded-disposition behavior when integrated.
- PR #2269 changes the owner-facing signed approval confirmation text to clarify automated independent verification (not a second human reviewer). This candidate changes the typed replacement decision/issuer branch, not the original callback success message; both intents can be preserved.

Do not merge this draft until changes are reconciled against the actual protected main and all required checks pass. Keep the engineering Owner pause and automatic-promotion hold intact.

## Gate verification after signed replacement implementation

- Exact PR implementation revision `9306f756046935474b4a91e26d86d1fad3d7b28b` and documentation follow-up `418da097d6bc1fb6569977b5d1a67ae2df2e70a8` were checked in an isolated worktree.
- Full combined Release Manager, signed mobile approval consumer and mobile-card tests returned exit code `0` on 2026-11-05; no production targets were used.
- All 42 PM V2 regression corpus tests passed locally. The earlier GitHub PM V2 failure was not reproduced; it remains subject to fresh CI.
- The read-only native offer selector against `release-54f4d2cdc048d805` selected `replacement_unfreeze_only` with the active freeze intact. This is not evidence of a signed Owner click or a successful deployment.
- GitHub integration acknowledgments for #2279 and #2269 are recorded in PR #2340 body. The change integration parser locally returns the exact acknowledged set `{2269, 2279}`. The previous job used a pull_request event snapshot from before the body edit and is not current acceptance.

This is bounded engineering evidence, not authorization to resume Owner-paused engineering workers, merge a draft PR, unfreeze production, or enable Autotask writes.
