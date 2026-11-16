# PMv4 A1 — one optional shadow-container admission into root-protected drift policy

**Status November 16, 2026:** SOURCE PREPARATION. No production root policy
modification or Owner authorization has occurred. Do not deploy A1 yet.

## Observed root refusal

The A1 local Owner launcher reached its root-only preflight and denied
`A1_SHADOW_NOT_ALLOWED_BY_ACTIVE_PRODUCTION_WATCHDOG`, before Owner
authentication, root staging, or gateway activation. Existing Ticket Core,
MCP, production freeze and promotion hold remain unchanged.

The active systemd drift service explicitly reads the root-only overlay
`/etc/jason/release-readback-recovery/production-desired-state.json`.
The protected Git source policy at
`8c2064193d74cc41b52369681febbc0a74fa96f7`
also omits `jason-pmv4-shadow-gateway`. The *actual* root policy is
inaccessible through unprivileged engineering tools. Its complete contents
and original bytes cannot be assumed to equal the Git source.

## Exact admission

- Add **only** `jason-pmv4-shadow-gateway` to
  `allowed_running_containers`. Do not add it to `required_containers`.
- Preserve all existing desired-state fields, unit requirements,
  arbitrary-container detection, prohibited execution paths, root ownership,
  drift watchdog, circuit breaker, release hold, production ticket processing,
  provider boundaries and existing LKG.
- Admission does **not** permit any container other than the named shadow,
  does **not** start the gateway, install code, grant provider credentials,
  enable production promotion, stop the watchdog or consume A1 approval.
- The root protected overlay may contain independently signed historical
  changes absent from the old Git source. A root update must be computed
  against **that exact live file**, preserving all its fields and old bytes.
  Never copy the proposed Git policy wholesale to the root overlay.
- Before an authorized update, record original root bytes SHA256, proposed
  exact one-name addition SHA256, immutable source and artifact SHA256, native
  host lock, Owner identity and one-use exact action. Preserve original root
  bytes in a root-owned 0600 audited rollback location. An attempted write
  must be atomic; on health/drift/control failure restore the original bytes
  and verify its hash. Production watchdog remains continuously enforced.
- Protect the root-only policy mode 0600 and directory boundaries. No manual
  editing, `chmod` shortcuts, disabling the watchdog, or bypassing its
  `undeclared_running_container` result.

## Source and read-only evidence prepared

This branch changes only one source config list entry. Tests assert the precise
one-name diff against protected main, optional-absence semantics, no drift for
that one approved container, and continued drift for unrelated containers.

`tools/pmv4_a1_watchdog_policy_review.py` is read-only, prints sanitized
original/proposed root policy SHA256, and refuses missing or non-root 0600
policy state, untrusted source schema, duplicate declarations, replays or
unrelated deltas. It never opens a writeable policy handle.

`tools/pmv4_a1_watchdog_policy_readonly_local.sh` is an optional exact
root read-only review launcher. It validates pinned script/config hashes,
protected source identity, tests and interactive Owner TTY; only after
`sudo` does it create a temporary root 0700 executable staging area under
`/run`, run the read-only inspector, then remove temporary staging. It does
not issue an Owner approval. Treat the resulting original root hash as a
precondition, **not** authority to mutate production.

## Required installation and release

No policy change should be performed directly from an editable source
worktree. An independently governed exact-Owner-signed root transaction must
verify the original live policy hash and apply the one-name optional allowance
under the native cross-release lock, with immutable original-byte backup,
rollback, independent drift PASS and Ticket Core continuity. That exact
signed policy update is separate from the A1 gateway release currently pinned
to protected source SHA `8c2064193d74cc41b52369681febbc0a74fa96f7`.

The release sequence must reconcile source identity: merging this PR into
protected main changes the source SHA and invalidates the *existing* A1 exact
source pin. Regenerate and re-review the A1 immutable release packet and
one-Owner scope after any protected main change, before authorizing gateway
startup. Do not reuse an earlier or failed release proof.

**Not yet proved:** live root policy original hash, authenticated policy-write
approval, policy migration/rollback, subsequent root A1 preflight PASS, actual
isolated shadow startup/health, rollback and independent C/D/E acceptance.


## Exact standalone root transaction prepared after successful Owner read-only hash proof

Owner's independent root-only report confirmed:
- Original active root policy SHA256: `4af577ccc02c367607da0c221c288df71ddc72bf4561ee6d7c6a35138f37e61c`
- Proposed exact one-optional-container root policy SHA256: `9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804`
- Protected main source SHA: `8c2064193d74cc41b52369681febbc0a74fa96f7`
- Reviewed proposed source config SHA256: `db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50`
- `root_policy_changes=1`, `required_containers_changed=false`, `other_root_policy_fields_changed=false`, `production_mutations=false`.

An independent one-time policy-release source was prepared in
`tools/pmv4_a1_watchdog_policy_root.py` with the local Owner entrypoint
`tools/pmv4_a1_watchdog_one_owner_local.sh` and the **existing** pinned Entra
OAuth / Ed25519 Owner signer used by A0. This is a **separate policy action**,
not reuse of an A0 approval or authority for starting the A1 shadow.

The release's immutable signed plan binds the reviewed protected main,
a retained reviewed configuration commit, the **current exact PR head**
(which may differ from the earlier source/config commit as tests are added),
the root installer SHA256, both original/target root policy SHA256,
one optional container name, production LKG, freeze, hold,
one authenticated Owner consent and no standing authority. If the proposed
PR moves after the Owner signs, the privileged source re-attestation DENIES.

Root preflight runs on a privileged `sudo` TTY from a copy of the reviewed
root script stored in a new root-owned `/run` 0400 one-shot directory.
It must prove original root policy exact hash, source blobs/PR CI,
a fresh CLOSED breaker and PASS drift, live Ticket Core/MCP health,
and both native legacy release and new PMv4 cross-release locks.
**No Owner signature is requested until all those conditions pass.**

After the single authenticated exact-action Owner decision, the root
transaction acquires both native release locks, writes an exclusive root
audit intent, durably backs up the **original exact policy bytes** 0600,
atomically replaces ONLY the named root policy file with the exact hash
of the one-container candidate, then independently runs the existing
production drift guard without disabling it. It checks protected runtime
and freeze/hold again, records one committed audit receipt and re-verifies
independently. If drift, Ticket Core, write readback or other postflight
denies before commit, it restores original bytes from the audited backup
under the same native locks and records a recovery receipt. A second
activation cannot reuse a root audit transaction or consumed Owner proof.

Disposable positive and negative tests verify: exact-byte original backup,
optional-only field semantics, successful atomic hash readback, native
lock held, rejected arbitrary replacement, failed-drift rollback to original
bytes, absent-Owner denial, actual Ed25519 exact-binding verification and
one-use replay denial, source head/installer hash binding. Tests are
**source-only** and do not prove a live privileged release or daemon rollback
after abrupt power failure. Future crash recovery requires independent
root audit inspection, not reusing an already committed Owner approval.

The older unsigned plan is archived rather than overwritten if the reviewed
root executor source changes. No source branch merge, live root policy
mutation, shadow startup, PMv3 retirement, service restart, breaker or
drift-watchdog bypass has been performed by this preparation.
