# Constant Contact OAuth-only MCP credential projection — governed activation

Date: 2026-11-12. Status: **source-only until root-installed and Owner authorized**.

## Objective

Bind the previously provisioned Constant Contact OpenBao AppRole to the existing, healthy production MCP callback process without updating runtime code, enabling imports or PMv4 Stage A0, activating a scheduler, or bypassing the production freeze.

**Baseline (independently observed at preparation):**
- Host, runtime and MCP revision: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
- Runtime image: `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
- MCP image: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- Original freeze SHA256: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`
- Root circuit breaker closed, fresh drift pass, no failed system units, MCP/runtimes healthy.
- Existing Owner Ed25519 signer remains in exactly one read-only MCP bind; unrelated `JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false`.
- Previously provisioned root-owned `constant-contact-oauth-client-approle/{role-id,secret-id}` are mode 0640, parent 0750, group al; OpenBao AppRole authenticated successfully, exact KV secret record version 1 and valid 32-byte AES key were independently verified without showing secrets.
- Callback `https://mcp-jason.teamaot.com/oauth/constant-contact/callback` exists in the current MCP image and returns HTTP 400 without valid state/code. The OAuth database has not yet been initialized, and no tokens have been issued.
- Protected main has an unrelated **PMv4 Stage A0 mode=on source change not separately approved for production**; do not promote broad current main solely to activate Constant Contact.

## Exact reviewed action and safety

The `tools/governed_provider_oauth_projection.py` implementation is an isolated root-owned **one-shot credential projection** built on the same independently tested Owner authentication, native live-container replacer and audit pattern previously used for signer recovery.

1. **No execution from a mutable worktree.** Root `python3 -I` must run an exact root-installed `/usr/local/lib/jason/governed_provider_oauth_projection.py`, with byte-for-byte root-owned manifest `/etc/jason-owner-release/constant-contact-oauth-mcp-projection.json`. Root file descriptors are opened `O_NOFOLLOW` with ownership/mode and exact source/deployer/Owner-auth-helper SHA256 validation.
2. **No privilege assumption from chat.** Before any Docker action the operator must complete a fresh Microsoft Entra device-code sign-in. The separately root-owned, exact-hash-existing Owner helper verifies Microsoft signed JWT/JWKS, exact AOT tenant, issuer/audience, scope and approved Owner object ID. Tokens and private credential bytes are not printed or persisted.
3. **Hard-pinned target.** Preflight checks the exact protected root LKG manifest, revision, runtime/MCP Docker image IDs, container labels, original freeze byte hash, fresh clean root drift, closed breaker, hardened non-root MCP, existing signer bind, `PMv4 Stage A0=false`, no preexisting Constant Contact mounts/env and root-owned AppRole files. Unknown/changed production state is denied.
4. **Only two read-only binds and three nonsecret vars.** The native, root-trusted deployer (existing SHA256 `2687a73e07d63693a057c3aa89cea0abb41d02cf1dcafb22df5ce82792c81eee`) replaces `jason-mcp-pilot` using the **same** immutable Docker image. It binds host `role-id` to container `/run/jason-secrets/openbao/constant-contact/role_id` and `secret-id` to `/run/jason-secrets/openbao/constant-contact/secret_id` read-only. It sets the corresponding environment path variables and `JASON_CONSTANT_CONTACT_OAUTH_DB=/var/lib/jason/openclaw/constant-contact/oauth.sqlite3`. The existing `/var/lib/jason/openclaw` writable mount is reused. No other service is restarted.
5. **One transaction, auditable.** The established production transaction lock is acquired exclusively after Owner authentication, held during the final state reread, mutation and verification, then released, so Release Manager and watchdog cannot race the controlled MCP replacement. The prior container is saved with the root desired-state-allowed `jason-mcp-rollback-` prefix, subject to the existing 20-backup retention gate. A root-owned 0700 ledger under `/etc/jason-owner-release/constant-contact-oauth-mcp-ledger` is claimed with `O_EXCL` **before** mutation; failed/complete receipts record only identifiers, timestamps and boolean outcomes. The new container must pass HTTP health, immutable image and source labels, identical old mounts/environment/networks/user except the two binds and three variables, preserved Owner signer, frozen host and exactly unchanged ticket runtime. Native deployer rollback or restoration of the prior named stopped container occurs on failed verification; no automatic retries after ambiguous states.
6. **Callback-only activation.** This does **not** set `JASON_CONSTANT_CONTACT_READ_PROFILE`, `JASON_CONSTANT_CONTACT_IMPORT_PROFILE`, `JASON_CONSTANT_CONTACT_RECONCILE_PROFILE` or PMv4 activation. There is no contact write, campaign send, list change, direct provider API bypass, new timer or release authority. External provider OAuth consent remains a separate interactive boundary.

## Verification sequence

- `python3 tools/governed_provider_oauth_projection.py --check-only` (nonmutating) → `READ_ONLY_CC_MCP_PROJECTION_PREFLIGHT=PASS`.
- Existing native deployer `--preflight` with exact same image and mounts → `PREFLIGHT=PASS`, 2 new read-only binds, 3 environment entries, no rollback alias changes. This was independently tested on the host and **did not** recreate a container.
- Unit/synthetic regression and GitHub CI on the final PR head: baseline and changed release conditions, preflight refusal for open breaker, stale drift, wrong images, missing signer, duplicate mounts/PMv4, exact postflight safety checks, one-shot claim, denied Entra flow and no secret logging.
- After exact root source/policy/ledger installation, the authenticated Owner must run isolated root `--execute` (explicitly approves a single brief MCP replacement, subject to health/rollback).
- Inspect the root ledger receipt from the Owner session and independently verify read-only mounts, same MCP image, signer still present, unchanged runtime container, freeze, closed breaker and drift. One must not claim success from a command exit alone.

## After MCP projection: bounded next stages

**OAuth connection:** The source-corrected Owner-local CLI `tools/constant_contact_oauth.py` on protected main already uses `role-id`/`secret-id`. Install it as a hash-verified root-owned CLI, invoke locally under `al` using the deployed canonical connector libraries, and open its one-time authorization URL only in the authenticated Constant Contact owner browser. Keep the callback's `state` and `code` private and valid for 10 minutes. The web callback exchanges and stores encrypted tokens; verify `CONSTANT_CONTACT_CONNECTED=TRUE` through local status, never inspect or print tokens.

**Account/list verification:** After signed consent, perform **only governed read** `marketing.contact.list.search` and `marketing.contact.search` with a separately exact-approved source-bound read profile, initialized shared account token state and read-only AppRole bind in the runtime. Verify the AOT account identifier and the intended destination list identifier against Owner confirmation; do not guess a list. Root-protected account binding is required before imports.

**Consent-backed import:** Obtain Owner-supplied Excel intake records and documented opt-in consent for a bounded 1–3 contact test, preview with source digest and suppression checks, use native universal exact-action approval and the dormant import pilot capability. No unaudited direct POST. Independently verify provider GET readback and whether subscription status/list membership match exactly.

**Scheduler:** Only after real provider acceptance and import readback, prepare separately approved source/host root allowlist migration for `jason-constant-contact-reconcile.service` and `.timer`, install them disabled then enable the independent GET-only timer, verify at least one cycle, immutable evidence, no duplicate POST and unchanged ticket-worker heartbeat. Both scheduler units remain unallowed in the current production desired-state and are intentionally disabled.

## Safety stop observed during engineering

At 2026-11-12T15:14:50Z, after the native non-mutating projection preflight passed, a SEPARATE systemd jason-openclaw-authority-health.service failure opened the root production breaker. The drift watchdog reported failed_system_unit and subsequently failed itself. This was not caused by source-only tests or a projected container change. The existing root-owned emergency fast-health adapter deliberately expired at 15:00 UTC; the full 36.6 GB orchestration audit and 4.1 GB authority SQLite integrity plus backup/restore proof had timed out after the 3,600-second bound. There was no full PASS snapshot to reuse. The adapter correctly stopped reporting degraded-read-safe at the fixed deadline.

Do not execute this projection while the breaker is open. The helper denies open breakers and stale or failed drift. Recovery requires an actually verified full integrity/restore proof and independent root revalidation, or a newly reviewed, explicitly Owner-authorized, bounded alternative diagnostic protocol. Do not extend an emergency expiry, mask failed units, clear root state without evidence, suppress drift or use direct Docker. If baseline images or revisions change during recovery, create a newly pinned projection.

## External authorization boundary

The connected session cannot install root-owned files into `/usr/local/lib/jason` or `/etc/jason-owner-release` unattended. The specific installation requires Owner's local sudo from the authenticated Jason host. After installed and hash verified, the root helper's fresh Entra Owner sign-in is the exact-action approval; no Teams card is required. Do not use raw Docker as a workaround.
