# PMv4 Stage A0 — one final Owner approval exact release candidate (NOT DEPLOYED)

**Date:** 2026-11-15. **Owner policy exception:** Explicitly recorded and approved in GitHub issue #2481. **Tracking integration:** draft PR #2493. **Status:** Independent production-root acceptance and CI pending; neither the chat's policy authorization nor a green source-only test is deployment approval.

## Exact signed native three-stage manifest

The existing Jason v1 Owner signer and root-pinned Ed25519 verifier provide **one signed and one-use exact whole-release approval**, with no new signer or Teams dependency. The original signed scope binds ALL three previously reviewed production effects in order, plus the exact candidate, rollback, source root executor SHA, freeze and hold:

- Root source-closure helper + policy + empty audit ledger, root-owned/0444+0400 (exact scope e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb)
- Exactly one missing root-owned/0444 immutable Git source file, byte SHA256 ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db (scope 089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381)
- Native source-pinned Stage A0 empty-baseline install, native scope 6786baad0fc9d07aca6ba80dedad5c25bcfa7fb3e50fdde7c4d36ad067285eac, exact manifest addba768d1ab92d9507d466fdd3980b93ea2041f42901f5d6e5a2cde81dcb025

**One signed full-release scope SHA256:** aea5374b13212b695f4d6428f860a172ecc901f90d97a7581a1a25bb492bf964. **One signed full-release manifest SHA256:** b6b7f9154729ef216ad2e26d7e3eeb0baa98ed1cfca2bea7ad9f1f86507b1b0c.

**Fixed executable root controller SHA256:** a72b0b17a5accd9f70835399caa8f2bc4fc803453945cb9d41fed01f5a087ba2. **Fixed root policy SHA256:** f95507fabb0084ed1cf3a31e4dbcba7076a73929da3fde8cf5cc36c162132cda. **Owner issuer SHA256:** 1b5e8612c774359e060f7b8f6618ef0479b7f42f4a0eb012f5ecff71dd71b3e1. **One Owner-local wrapper SHA256:** c255b4d535c9961e5e123f57980163c15bafd84100f4e5abbd32c45a666b9498.

Production LKG remains d1b8c196dadd4b672ec8ba47075f27bb61c98d63; candidate immutable source 7b42ce983896711525de4c7955bf9fc43ac003d0. Freeze remains bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f. Promotion hold remains 11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0. Existing Ticket Core/MCP images and current release pointer remain unchanged by this source-only preparation.

## Trusted execution boundary

The fixed Owner-local wrapper is `tools/pmv4_a0_atomic_one_owner_local.sh` in the exact #2493 integration worktree; it runs **only in an interactive local Jason UID1000 terminal**, never directly through Remote Desktop Commander's blocked sudo channel. In its `--execute` mode, it verifies exact root/issuer/bootstrap/policy byte SHA, then installs only those immutable scripts as root:root 0400 under an exact private root-owned 0700 `/run/jason-pmv4-a0-atomic-v1-7b42` staging directory; a root script `--preflight` independently verifies protected current source/CI, all four original SQLite integrity proofs and backup/restore, active fast health and root breaker, full runtime/MCP identities, existing root source 13-file baseline, root-only native target absence, original freeze/hold hashes and lock. **Only after that root preflight passes** does the launcher request **one** verified Microsoft Entra Owner device-code login and one typed exact-action confirmation covering all three operations. The existing signer writes one 0600 source-bound Owner proof. The original pinned root-owned verifier independently checks it. Only one root transaction is then allowed.

The root executor maintains the existing native host release lock across all three exact changes, plus the native scoped host-mutation lock, fsync's a root-owned append-only hash chained release journal and records intent before each write. Every action and resulting file is checked independently before the next step. It commits success only after all three postflights, preserves the original global freeze and hold, and automatically attempts conditional reverse rollback to the previously empty state if any step fails. It cannot delete foreign/changed objects and records requires_review if rollback is not independently safe. After a crash, `--recover` may verify the original signed Owner proof at its historical issuance and perform ONLY rollback (never an unauthorized forward retry). The wrapper invokes `--postflight` and only then reports success. It retains immutable root stage files if recovery is incomplete.

**Important authority boundary:** the project-specific Owner answer **Yes** approved aggregation of these three A0 transitions into one future exact release, NOT the final authenticated production deployment. Do not execute this candidate until the exact-head independent CI including disposable true UID0 root end-to-end tests, formal code/security review and live root-only preflight (performed by the one Owner-local launcher *before login*) have passed. The source-only files cannot execute root from an untrusted checkout. No preexisting A0 source module/root helper is present yet.

## The single future Owner action — ONLY after confirmed final GO

```bash
bash /srv/jason/archive/engineering-worktrees/pmv4-a0-atomic-oneowner-20261115/tools/pmv4_a0_atomic_one_owner_local.sh --execute
```

One local command starts independent root preflight **before** prompting for Entra. If the preflight fails, the Owner's one final approval has not been spent and the operation stops with production unchanged. If preflight passes, one Entra authentication and exact confirmation authorizes the complete bounded one-use operation; no additional per-stage approval. Only the signed, independently verified full release manifests gain that narrow exception to the frozen production state. No standing root/Owner authority is conferred.

## Evidence boundary / status

Unprivileged `--check-only` and exact issuer read-only preflight PASS on Jason without consuming Owner approval. Initial source-only native three-stage atomic acceptance and one-v1 whole-release tests passed. The production root-only preflight cannot be executed from ChatGPT's blocked sudo channel and has NOT happened. Real deployment and postflight have NOT happened, and must never be inferred from this document. Independently passing root-mode CI and code review remain prerequisites before handing the single Owner action over.


### Final full-health commit and post-commit recovery safeguard

The root executor now independently runs the **same complete privileged three-stage postflight** (bootstrap helper/policy/ledger, full 14 pinned immutable sources, native A0 complete exact objects and chained original signed audit, live production Ticket Core/MCP/scanner and root breaker, genuine 4-SQLite/backup+restore plus fresh fast health, unchanged freeze/hold/LKG) BEFORE append of the one-use global `committed` record. A failure at this stage initiates audited exact reverse rollback while the existing release lock remains held. The optional separate `--postflight` readback is retained to independently verify completed state. If that subsequent readback detects a failure after `committed`, the one-time `--recover` path allows **only exact rollback** under the original signed Owner proof, never a forward retry, only when the same independent complete postflight demonstrably fails. Healthy committed releases deny rollback. An existing native breaker/MCP health outage cannot itself block corrective rollback: the rollback context verifies exact root identity, source SHA, rollback inode+bytes, freeze/hold and LKG but intentionally does not demand live root breaker CLOSED. Foreign or unverifiable objects remain quarantined, not deleted. UID0 CI exercises success, failure at all three real effects, full-precommit postflight failure, confirmed postcommit health failure reverse rollback, committed healthy rollback denial, replay and tamper. The existing native `IndependentHostGuard` breaker/MCP/scanner checks run immediately after the new Stage A0 objects are created and again at the final full postflight. No extra human Entra approval for rollback or interrupted recovery.
