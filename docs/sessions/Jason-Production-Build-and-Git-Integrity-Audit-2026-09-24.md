# Jason Production Build and Git Integrity Audit — 2026-09-24

## Purpose

Verify that the post-power-failure Jason environment has no Git corruption, stale production source boundary, unsafe branch/worktree residue, or Docker image-alias drift that could cause an unexpected build, restart, recovery, or deployment result.

## Git and GitHub result

- `git fsck --full --no-reflogs` completed without missing/corrupt objects. Reported dangling blobs/trees/commits are normal unreachable history from prior squash/rebase/branch cleanup and are not repository corruption.
- Authoritative `main` at the audit start was `699bf0a836888ca0565369ba7a8db8f0c115caf0`; all current `main` push validation workflows passed.
- `main` protection remains strict, applies to administrators, requires the always-on CI matrix and resolved conversations, and blocks force-push and deletion.
- The path-filtered `Validate MCP Capability Discovery` workflow intentionally remains outside the global required-check set because unrelated PRs do not trigger it.
- Stale local/internal-company and boot-recovery branches/worktrees were removed only after proving their durable content was already present in `main`. The boot-recovery controller, service, and timer were byte-identical between the stale branch and `main`; the branch divergence was squash/history noise plus an older runbook.
- Local worktrees were reduced to authoritative `main` plus active Backup.net work. Remote non-main branches correspond to active open PR work.
- Open PRs #218, #222, #226, and #227 had passing GitHub CI and GitGuardian checks at audit time.

## Production runtime result

Observed live production before any correction:

- runtime source revision: `699bf0a836888ca0565369ba7a8db8f0c115caf0`;
- runtime image: `sha256:11201164eac42df7405bc08c5eb6cf9a909af74e5ed6232a819ed9f95054bfb9`;
- MCP source revision: `699bf0a836888ca0565369ba7a8db8f0c115caf0`;
- MCP image: `sha256:7c4b082fa0b0b8aa992d04b3935d5711893e503ae7c1685303194551cd552ca5`;
- runtime health: healthy;
- restart policy: `unless-stopped` for runtime and MCP;
- root filesystem usage: 48%;
- inode usage: 22%.

The running containers were correct, but canonical image tags were stale at the previous `3cb1c4e` release and `:rollback-current` was older still. That state could have caused a future compose recreate, baseline refresh, or default production deployment to select the wrong image.

## Immediate non-disruptive correction

Without restarting production or contacting a provider:

- retagged the actual live runtime image as `jason-runtime:production` and `jason-runtime:local`;
- retagged the actual live MCP image as `jason-mcp:production`;
- rotated the previous canonical/runtime image `sha256:2b8f4e0505b0c90046b1909105d4a9a4bae07ecce7e182007c13a6cc19332cc1` to `jason-runtime:rollback-current`;
- rotated the previous canonical/MCP image `sha256:bfcfe37d45cc223398a243f2ff67c5c1845217f0aa91c4061d535de9d182a372` to `jason-mcp:rollback-current`; and
- verified canonical tags exactly match the running images and rollback tags identify source revision `3cb1c4e6829a595cf76207163c4bbe658c6f7cb0`.

## Permanent deployment correction

The governed deployment helper and production wrappers now make image-alias state part of the deployment transaction:

1. snapshot existing canonical/rollback aliases;
2. preserve the exact pre-deployment live container image identity;
3. deploy and verify the candidate container;
4. require hardening and health verification;
5. rotate the actual pre-deployment live image to `:rollback-current`;
6. promote the verified candidate to canonical production alias(es);
7. verify the resulting alias image IDs; and
8. if alias promotion fails, restore the previous alias snapshot and execute the existing fail-closed container rollback path.

Runtime promotes both `jason-runtime:production` and compatibility alias `jason-runtime:local`. MCP promotes `jason-mcp:production`. Re-deploying the same image does not overwrite a known-good rollback alias with the same image.

Focused tests cover successful promotion, actual-live rollback selection even when the prior canonical alias was stale, same-image redeployment, and restoration of prior/missing aliases.

## Security and provider boundary

This audit and correction performed no Autotask, Datto, Microsoft, Teams, or other provider mutation and required no production container restart.
