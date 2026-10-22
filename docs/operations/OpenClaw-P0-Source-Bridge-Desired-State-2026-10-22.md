# OpenClaw P0 source-bridge desired-state registration

**Status:** source-only recovery repair; not a production deployment or a new worker role.

## Observed failure (2026-10-22)

An authorized read-only evaluation of the installed production drift guard returned three problems: the host-installed `jason-openclaw-recovery-source-bridge.service` and `.timer` were undeclared user units, and `jason-production-drift-watchdog.service` retained a failed systemd state after reporting drift. The OpenClaw P0 recovery bridge timer itself was active. The production code remained at `aca94fdc0bfa551162f6ea99d7ddded311786414`; merged source at `94465e54fadc6a2e0dc9b3d9c0d33f642e07f653` had not been deployed.

## Bounded registration

`config/production-desired-state.json` now lists **only** the exact two existing P0 bridge user units under `allowed_user_units`, not `required_user_units`. This recognizes an already owner-approved temporary source-recovery pilot; it does not enroll a different host, authorize new roles or shell access, or grant approvals, provider writes, root authority, release deployment or production control to OpenClaw. The source-bridge remains restricted to validated source proposals and the native GitHub PR review path. It is not an end-to-end governed development worker.

The drift guard retains normal detection of unexpected user/system units, forbidden paths, failed services and container drift. Regression coverage asserts that the two precise pilot units are permitted while a third `jason-unreviewed-worker.service` is still rejected. The checked-in policy remains authoritative only after a separately governed exact-revision release.

## Remaining independent recovery gates

1. Protected CI, required independent review, immutable candidate preparation and isolated preproduction must pass.
2. Any production promotion must satisfy exact candidate authorization, root-controller/CCC checks, and rollback verification; a merged policy is not an installed policy.
3. The existing failed `jason-production-drift-watchdog.service` state requires independent diagnosis and a governed root/operator recovery after the actual drift cause is corrected. Do **not** mask it, delete the root evidence, manually replace the protected desired state, or make forced CCC ignore failed systemd units.
4. Verify fresh protected drift evidence, correct production SHA, CCC/last-known-good alignment and the circuit-breaker state.
5. Only after native reasoning has produced a genuinely successful new `search_plan` or `edit_plan` reply and the merged retry repair is deployed may existing blocked development work be admitted under its exact-once safeguards. No historical retry ledger is reset.

When the pilot is retired, remove both optional entries through the same governed versioned process and retire the corresponding user units under the approved P0 cleanup plan.
