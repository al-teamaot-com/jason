# IT Glue read AppRole: one-provider Owner-governed recovery (2026-11-12)

STATUS: DEVELOPMENT ONLY. NOT INSTALLED, AUTHORIZED, EXECUTED OR PRODUCTION ACCEPTED.

## Verified production diagnosis
- Live governed documentation.organization.search still returns OPENBAO_AUTH_FAILED.
- Root-managed boot recovery on current production reports RUNTIME_CREDENTIAL_STAGING=ALREADY_CURRENT. This proves protected and staged bytes match, NOT that the AppRole identity is valid.
- Governed Autotask ticket reads succeed; worker scans remain current.
- Earlier generic OpenBao identity lifecycle service is no longer installed; do NOT re-enable its unrestricted worker.
- Current protected production source last verified: d1b8c196dadd4b672ec8ba47075f27bb61c98d63.

## Source-only targeted repair
tools/it_glue_approle_recovery.py implements a fixed, single-provider recovery of IT Glue READ authentication only. It NEVER provisions IT Glue write access, changes the API key, alters Vault policies, handles passwords, invokes arbitrary providers, or restarts services itself.

The code is inert unless independently reviewed and merged, released by the native PMV3 mechanism with exact signed Owner approval, and separately installed as exact root-owned byte-matched copies of BOTH the helper and tools/provider_secret_provision.py under /usr/local/lib/jason.

A true local Owner action requires: root with SUDO_USER=al, a real console, authenticated exact signed native release record in Closed state, exact running source SHA, explicit action-approval reference, and the locally typed challenge AUTHORIZE IT GLUE READ APPROLE ROTATION AND BOUNDED RUNTIME REFRESH. The OpenBao al-admin password is entered in a hidden local terminal prompt; never enter credentials into ChatGPT, GitHub, CLI arguments, or logs.

After local Owner approval, the helper: verifies immutable source and role identity, authenticates the OpenBao administrator, creates a durable one-shot claim BEFORE any SecretID creation, tests current identity, creates at most one new SecretID if necessary, independently verifies new login and KV read using only the fixed IT Glue READ secret contract, atomically stages the new protected source only after these checks, and records sanitized result. It does not expose or hash RoleID, SecretID, token or API key. Any ambiguous state remains claimed to prevent unsafe repeated rotation.

The installed root-managed boot-recovery timer will detect a protected-secret change and may perform a bounded runtime remount. This is a potentially disruptive action and must be explicitly included in the local Owner approval. Do not restart services, disable drift or use direct provider access as a workaround.

Afterward verify live governed IT Glue reads, Autotask reads, ticket-worker scan heartbeat, runtime/MCP health, protected freeze bytes, immutable release source/image and rollback. Archive sanitized evidence in the independent immutable evidence system. Do not revoke any old identity before acceptance.

## Future local run (only after signed exact-source release, root install and separate approval)

First perform a read-only, verified preflight from the *root-installed* helper:

    sudo python3 -I /usr/local/lib/jason/it_glue_approle_recovery.py --check-only --source-sha APPROVED_EXACT_PRODUCTION_SHA

Then only after the separate exact Owner action and bounded runtime-refresh approval:

    sudo python3 -I /usr/local/lib/jason/it_glue_approle_recovery.py --apply --source-sha APPROVED_EXACT_PRODUCTION_SHA --approval-reference APPROVED_EXACT_ACTION_RECORD

Do NOT run from any Git worktree or group-writable production tools directory. This remote session cannot perform that local human approval, protected root installation, or OpenBao password entry.

## Write access remains separate
The dormant write adapter is in draft PR #2455; its last reviewed head is 920bb248fd9cf254b69d04e3d91d4d9c17f6da68. Before any provider write: restore the read identity, verify a real disposable AOT-controlled IT Glue test organization and validated Jason client mapping; create a separately authorized IT Glue write API key in IT Glue (not the existing READ key); provision and stage the independently scoped it_glue.readwrite OpenBao credential using the root-governed provisioning mechanism; bind exact client/requester authority and J-102 approval. Test one metadata-only create and one update, each with independent governed pre/post readback and negative cross-client/restricted cases. Do not silently retry ambiguous creates, activate broad CRUD, or touch production client data.

## Verification scope
Source-only pytest negative/positive cases cover role mismatch, missing root/local identity, valid identity no-op, new SecretID login and KV contract before mutation, provider error redaction, invalid new identity rejection and single-provider boundaries. Mock tests do not prove live provider operations.

REMAINING BLOCKERS: exact Owner-approved root installation and local protected credential operation; live provider read acceptance; dedicated IT Glue write key; verified test organization and live create/update; separate exact signed production release approval for enabling writes.
