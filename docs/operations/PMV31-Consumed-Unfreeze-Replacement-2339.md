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
