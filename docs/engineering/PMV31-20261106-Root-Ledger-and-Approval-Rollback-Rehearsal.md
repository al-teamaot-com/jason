# PMv3.1 actual-root-ledger and approval-service rollback evidence (2026-11-06)

## Verified protected read-only facts
The Owner-executed root-only read-only audit found two applied receipt levels:
- Level 0: candidate 7e7b13af05881201a683624a2e40509ebbd79b78 (Teams approval-only timer/service), rollback c2b559488d761cb10a6da35092b391de5b5e9c69; root policy after this level: SHA256 afc2b58d2cfbdc81d0e98ecf2ec121c3877894cfd0f830db5a949b3dab75b038.
- Level 1: candidate 743c75eaa541dfcb1efb1cd80746728395fcfe97 (authority-integrity systemd units), rollback aca94fdc0bfa551162f6ea99d7ddded311786414; prior applied policy SHA256 6473be851479381982d9232e55a5400a7e0a9890bc7715fcf5172c33553720a0.
- Original protected policy hash: 709164967c5d5dd0982d9774a1bfeb8f1aa3668d6d6e4e43c6eec209d389a82a.
- The original active receipt SHA256 was a08b7a7474f1191eaa6fe58c229a3dbe10f5b5818117b561aa2a4eb12346ce8a. Do not claim fixture receipts are byte-identical to this protected receipt. They are synthetic receipts with the same reviewed SHA, delta, phase, ancestry and policy hash structure.

These three historical policy hashes were **reconstructed exactly** from the protected-main Git history; no root file was copied or modified. The strict Git ancestry edges were separately verified on Jason.

## Why the earlier releases failed
- The old root validator allowed only a single historical applied predecessor. The deployed baseline already had two receipts. When PMv3.1 attempted another migration for its *exactly two optional provider-health system units*, the native root host reconciler failed closed with `MigrationRefused: nested root migrations require separate review`.
- The native automatic rollback restored the old LKG's approval-only user service with `--repo /home/al/.local/lib/jason/engineering-worker-source`. That checkout has a different Git worktree registry and causes manual scope digest mismatch for new signed release approvals. The production drift watchdog correctly detects the resulting failed user unit.

## Rehearsal coverage
The hermetic `tools/tests/test_pmv31_real_root_chain_acceptance.py` uses the original policy byte fixture `pmv31_authority_original_policy.json` plus exactly the two reviewed historical overlays. It asserts historical original/applied SHA256s, exact source/rollback lineage, a third exact PMv3.1 root migration, symmetric rollback preserving every predecessor receipt byte, staged and applied forced rollback, and fail-closed behavior for corrupted ancestry.

The user-service acceptance tests install a reviewed `jason-release-approval-only.service.d/10-canonical-release-scope.conf` and then **reinstall the actual LKG service bytes** from `pmv31_baseline_approval_only_unit_ee8d0652.service`. They verify the service's effective command remains bound to the canonical shared-Git worktree, the original Owner hold stays in the base unit, and unknown/tampered/symlinked drop-ins are refused. The old LKG host scripts only copy the base service/timer; they do not delete approved drop-ins.

Two independent combined-sequence tests run the actual protected-policy stage/apply/restore functions and the real approval-only unit installer using a temporary nonproduction user-unit directory. They then reinstall the actual prior LKG unit bytes and verify that the reviewed source override remains effective, while the original root-policy bytes and prior receipt bytes match exactly. The component regression and negative tests include refusal of tampered or symlinked overrides and historical ledger corruption.

These are **isolated component-integration rehearsals**, not proof of successful live production deployment. Production still requires exact-SHA signed Owner/CCC decisions, independent root helper bootstrap, one-time freeze approval, native host-reconciliation, and independently verified postflight and rollback.

## Safety boundaries
Never delete or reset root migration receipts. No direct provider writes, no privileged production writes, no production freeze change, no host or endpoint reboots, no standing release authority and no bypass of protected main.
