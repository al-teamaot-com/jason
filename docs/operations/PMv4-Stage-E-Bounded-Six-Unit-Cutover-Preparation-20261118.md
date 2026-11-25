# PMv4 Stage E — bounded six-trigger cutover preparation (2026-11-18)

**Disposition: PREPARATION ONLY; NO-GO for production retirement.**
This source review is not an authenticated Owner approval, an executable root
transaction or evidence of live six-function parity. It deliberately creates
no root or production mutation.

## Observed live baseline (2026-11-18 UTC)

Read-only Jason-host checks:
- Current installed production revision:
  `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Six legacy production triggers active: three user timers and three system
  timer/path controls; six proposed PMv4 triggers inactive.
- Root acceptance marker
  `/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json`
  absent, and `/opt/jason/pmv4-e-trusted` not installed.
- `jason-runtime`, `jason-pmv4-ticket-core`, and isolated shadow healthy
  by Docker status; `jason-core.service` active. The protected production
  drift timer and user self-heal timer active.
- Read-only retirement readiness: `not_ready_for_pmv3_retirement`;
  fresh ticket scan at 19:52:24Z with 139 provider items, 138 evaluated,
  zero duplicate items. It does not independently establish C/D/A1
  root receipt integrity.
- The privileged protected desired-state file could not be read through
  the existing unprivileged remote command boundary. Do NOT substitute
  checked-in source for root policy verification.

## Exact proposed six-unit delta (not applied)

| User trigger retired | New user trigger |
| --- | --- |
| jason-support-repair-worker.timer | jason-pmv4-engineering.timer |
| jason-release-approval-only.timer | jason-pmv4-release-approval.timer |
| jason-release-manager.timer | jason-pmv4-component-release.timer |

| System trigger retired | New system trigger |
| --- | --- |
| jason-release-control-transition.timer | jason-pmv4-component-transition.timer |
| jason-release-control-readback.timer | jason-pmv4-component-readback.timer |
| jason-release-host-reconcile.path | jason-pmv4-component-reconcile.path |

Candidate source-policy canonical SHA256 (model, not live root):
`da1e52e3d562f4ae3795deafb21ffc32043b13b0b256ce1ce2944a2800bc5f0a`.
Prior source-policy canonical SHA256:
`9c126fbdba84167851621b9e1efe3c6ad107d6b9c86e1ee47b6a3a2a179dcd34`.
Checked-in policy raw-file SHA256:
`db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50`.
**These values are NOT an approved live protected desired-state hash.**
Existing recorded protected desired-state SHA256 `4c9db0f4...` must be
re-read independently at root before selecting any transaction.

## Reused implementation, no parallel release engine

- Source PR #2587 (merged `54fa7fd5...`) prevents root reconciliation from
  reinstalling PMv3 after a trusted cutover receipt.
- Source PR #2588 (merged `1d6e5aa5...`) makes canonical release-manager
  scheduling, installer verification and manifest alignment aware of trusted
  PMv4 replacement; it denies legacy timer resurrection.
- Existing watchdog retargeting uses the existing production transaction lock.
- The six replacement units reuse previously approved backend entrypoints
  and require the preinstalled root-owned exact unit admission guard.

## Preparatory isolated verification

- The 12 new unit files pass `systemd-analyze verify` with return code zero;
  the only observed warning concerns unrelated existing `cag.service`
  `KillMode=none`.
- Source-only `pmv4_e_six_unit_transaction_model.py` simulates seven ordered
  operations with seven post-step injected failures and exact state restoration.
  Its first 16 focused tests passed on the Jason host.
- Simulation does not prove real systemd activation, provider-independent
  scheduling, approval continuity, native/root release or crash recovery.
  The model reports `root_transaction_implemented=false` on purpose.

## Required root-owned, exact-governed transaction (NOT YET IMPLEMENTED)

Only the established native root Release Manager/controller may execute this
transaction. The final trusted implementation must **not** invoke a generic
shell or a new ungoverned release engine.

1. Bind one fresh authenticated Entra Owner authorization to **the final
   immutable source commit, exact scope digest, complete prestate, exact
   provider-free six-trigger delta and rollback identity**. Verify signature,
   audience, expiry, one-use grant, root trust and release lock.
2. Re-read root-only C/D/A1 acceptance, shadow hash-chain, native canary
   acceptance, actual protected desired state and freeze; reject any drift
   from accepted pinned values.
3. Capture root-owned immutable before-image of six old unit files, states
   (is-active/is-enabled), old/current policy, user timers, watchdog target,
   manager controller installation, root host reconciliation and their
   pinned SHA256s. Audit the complete existing durable work claims.
4. Install only the exact reviewed new root/unit guard and 12 new unit
   files as **inert**, while the old callbacks remain enabled.
   Verify all source hashes, root ownership and the expected denial before
   acceptance. Never restart Ticket Core, MCP, Runbook or shadow services.
5. Under the existing shared production release/dispatch lock, checkpoint
   pending claims and stop/disable only the exact six legacy triggers.
   Confirm no old callback is in flight and no duplicate work ownership.
6. Atomically swap only the reviewed desired-state six-trigger delta,
   watchdog target and canonical root/Release Manager convergence code,
   with protected root journal and immediate inverse rollback.
7. Write the exact root-owned accepted marker only after installed root
   admission and release evidence match. Activate the six new triggers,
   release dispatch lock, then verify five-minute engineering claim/retry,
   release approvals, component release, transition, readback and reconcile.
8. Verify two distinct real Ticket Core scans, one dispatch owner,
   zero duplicate provider items, scheduled work continuity, runbook
   lifecycle, component release and bounded rollback, notifications,
   provider read canaries, immutable evidence, breaker CLOSED and live
   drift PASS. No paid-model fallback.
9. On any failure, first revoke cutover acceptance under the root lock,
   block new callbacks, restore exact prior policy/installer/watchdog and
   six prior unit states, then prove active monitoring, zero duplicate work,
   unchanged freeze and core/MCP digests. Preserve the complete audit chain.

## Hard NO-GO gates before requesting Owner consent

- The exact privileged root transaction/rollback executor and installation
  must be independently reviewed and exercised under disposable UID 0.
- All six callbacks must be observed under provider-free isolation with
  legacy triggers disabled, including interruption/resume and durable claims.
- Root-owned C/D/A1/canary receipts, live protected desired-state policy,
  release SHA and exact rollback objects must pass *fresh* readback.
- Final immutable scope hash, release candidate SHA, Owner action payload,
  expected current production SHA and rollback SHA must be finalized.
- Existing production freeze remains intact; no generalized override.
- Require one final fresh exact Entra-authenticated Owner approval after the
  above checks. A chat instruction to continue engineering is not a
  deployment grant.

## Current decision

Engineering may continue; production cutover is **NOT AUTHORIZED** and
**NOT READY**. Do not disable the six old units. No Owner interaction
is needed for source-only engineering or read-only evidence collection.
