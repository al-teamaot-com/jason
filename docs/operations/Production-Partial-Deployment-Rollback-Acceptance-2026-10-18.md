# P0 Production Manager: crash-consistent rollback and mandatory CI tests

**2026-10-18.** Dependency: #1078 and recurrence #1055/#1437. Scope:
**source + isolated fault-injection only**, not production rollback authority.
Both high-risk Teams approval modes remain OFF.

## Verified starting state

Owner-approved **exact SHA** `212725957619af4871df6a235e31943f4d5e0972` was successfully
promoted on 2026-10-18 at 13:50:32Z. The real host reconciler, Grafana,
mandatory authority-health snapshot, complete 13-check postrelease CCC,
runtime/MCP/host/controller version alignment, runtime HTTP 200, immutable
new last-known-good manifest, and protected drift PASS were all independently
read back. This validates **one successful production release**, not a
failed-release recovery.

The prior `release-b1ea8751af208a76` had FAILED its root rollback host
reconciliation with `rollback_verified=false`. Subsequent aligned live
readback does not retrospectively certify that failed transaction.

## Actual latent defect reproduced by isolated fault injection

The canonical `_deploy_production_locked` previously marked
`runtime_deployed` and `mcp_deployed` only **after** each deploy script
returned exit 0. But `deploy_live_container.py` can stop, rename, start, or
retag containers before returning a failure. Its internal rescue intentionally
uses some `check=False` Docker recovery commands, so that recovery cannot be
assumed successful. Two explicit tests simulated a candidate runtime or MCP
swap followed by nonzero script completion. **Old code left the partially
changed surface on the candidate SHA** and could not verify rollback.

A second real configuration concern was observed read-only: after the
successful release, `jason-runtime:rollback-current` and
`jason-mcp:rollback-current` still point to older
`ad11c311...` images, while the current complete root LKG is
`212725957...`. This is normal tagging history when no next release has
completed, but a failed forward helper **before retagging** cannot safely use
those aliases as the rollback target.

Furthermore, three of four existing atomic tests were failing **before
entering a deployment path**, because their fixtures predated the mandated
`release_manifest` and `risk_profile` contract. The protected
`repository-hygiene` job only ran unit-test classes; the actual pytest
atomic transaction suite was absent from required CI checks. Hence prior
required-check green did **not** prove the atomic rollback tests passed.

## Bounded recovery hardening

1. Mark both the runtime and MCP forward scripts as **attempted before
   invocation**. A nonzero script result may have left real side effects.
2. For each attempted surface, independently inspect the live revision,
   actual immutable image ID, production image tag and runtime health/running
   status. If all match the captured LKG manifest, record
   `already_verified_at_baseline` and **do not restart healthy containers**.
3. Otherwise, verify the rollback artifact is an exact sha256 image ID from
   the captured pre-mutation manifest, retag **only the fixed canonical
   rollback-current alias** if it is stale, and read it back. Only then
   invoke the existing governed candidate deployment script in rollback
   mode and independently check the restored live revision, image ID and
   promoted alias. A missing image, uncertain PID/state or bad tag fails
   closed; never accept an unverified rollback as success.
4. Preserve original reverse dependency order: MCP, root host
   reconciliation, Release Manager, runtime; any failed independent root
   host reconciliation makes the whole rollback **unverified**, even if the
   three service revisions later look aligned.
5. Require **read-only full-manifest verification** after recovery,
   including runtime health, MCP, immutable host, controller and scheduled
   timers; compare recovered immutable image IDs to the originally
   captured LKG. Avoid redundant Release Manager reinstall/restart only
   for final verification. Persist per-surface
   `failure.rollback_actions` distinguishing untouched, restored,
   already verified and unverified outcomes. The existing circuit breaker
   remains mandatory for *every* failed transaction, even after an
   independently successful rollback.

No provider access, new shell authority, approval relaxation, manual Docker
mutation, production test container or alternative release writer is added.

## Tests and required CI enforcement

Updated obsolete atomic test records to include canonical exact-SHA risk
classification and release manifest. Their external Docker, host, CCC,
GitHub and root file calls are mocked without disabling the actual release
contract validator or rollback flow.

Isolated unit scenarios cover successful forward closure; forced
post-deployment final alignment failure; independent host timeout during
rollback; partial runtime and MCP script failures **after simulated swaps**;
stale rollback tag pinned from exact LKG; rejection of an unretaggable image;
preflight failure leaving the baseline untouched without a restart; root host
absence before mutation; and protected image provenance.

The protected `repository-hygiene` GitHub job now installs pytest and
**must run** the atomic transaction suite plus root-host reconciler,
exporter-port guard and mandatory-health timeout tests as part of the
required PR check. This closes the blind spot where stale tests were not
being evaluated.

## Acceptance still required before claiming full reliability

This is an engineering patch tested in mocked/isolated execution. It does
**not** constitute a real fault-induced rollback in production. Following
protected source review/CI, any future release must be prepared from a
new exact merged main SHA and pass canonical isolated preproduction.
A **new** Owner exact-SHA authorization and fresh CCC are required before
any production deployment. An actual controlled, non-customer-impacting
failure/rollback drill needs a separate, explicitly scoped Owner action
approval. Do not reuse the old `212725957...` deployment grant for a
different SHA.

Do not close #1078 or #1101 until a genuine failure-path drill independently
proves root reconciliation on rollback, full LKG identity, CCC/drift and
circuit breaker behavior. UTA/v2 protected approval remain separate.
