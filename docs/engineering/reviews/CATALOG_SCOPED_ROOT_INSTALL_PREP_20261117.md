# Catalog runtime/MCP — exact root installation preparation (source only)

**Authorized scope:** Prepare the root installation and rollback package necessary to enable the already merged catalog-only scoped promotion transaction. **Not authorized:** root installation, replacing the live root host-reconcile worker, starting a recovery timer, unfreezing production, promoting images, making Autotask provider writes, or broadening any Owner allowlist. No independent human security-reviewer step is part of the Project Jason governance model; existing protected-source CI and exact Owner approvals remain mandatory.

## Baseline checked on Jason on 2026-11-17

- Protected source that introduced v2 catalog admission: `1b804ea6cff8efedc4f9b29b3dddaf45e86e8f82` (PR #2538); scope/transaction source: PR #2537.
- Original live host and both running containers: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Runtime rollback image: `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`.
- MCP rollback image: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
- Original active production freeze SHA256: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.
- New isolated approved-for-read-only-admission candidate source: `755fa5fe3f75958fee2427a0af0777dd242d8f00`; runtime and MCP v2 Docker image IDs `sha256:dbd4d017dcc2deaf83109f5a0c6e68b3473c6de13881a56aa17238b647bbce66` and `sha256:da57dd05bfde19321ddb4eca2b1910aff41aee7027905365fdb76a12aa1989f2`.
- The v2 read-only admission completed with receipt `add8327f9cb6b0cdc9cb9a6006d8038ec71ed2b914e3e1fd6a144f7a55392272` and the **unsigned** scoped promotion offer hash `4712f94dc35e1d6781fe6e8c02b57278da9bd0f10ebedaea130c2934f1b5f45b`. Neither represents production release authority.
- Current deployed root worker is root-owned mode 0755 and the root-pinned Owner public-key trust file is present; the current native release lock is `al:al` mode 0664 and the production control state remains root-owned mode 0600. The catalog root installation policy is absent, and the catalog recovery timer is not found.

## New deterministic, read-only installation plan

`tools/catalog_scoped_root_install_plan.py` is an operator-readable, source-only utility with **no `--apply` mode**. It binds current protected Git `main`, historical and fresh read-only catalog receipts, immutable isolated candidate and rollback image digests, the original frozen marker, the installed root worker hash and pinned Owner verifier, exact source blob digests, and a plan hash. It hard-rejects drift from `main`, a different host revision, a modified freeze, extra source paths, missing root trust or silent assumption that the root adapter is already installed.

The proposed installation scope contains exactly 17 source files in the immutable bundle. Two source files have additional active installation destinations: the existing root host-reconcile worker path and the two catalog recovery systemd unit files. It plans the native root policy at `/etc/jason-owner-release/catalog-scoped-promotion-installed.json`, a root-only transaction/recovery ledger and an al-owned exact catalog Owner-signature handoff under the existing `/var/lib/jason/authority` mount. The active production Docker containers are **not** part of this install plan; image promotion requires a distinct signed Owner release.

The plan also computes a separate **installation_scope_sha256**, binding the exact protected source, target file paths/digests, previous root-worker digest and freeze. This installation scope is deliberately distinct from the catalog image-promotion scope and unsigned promotion manifest, preventing a signed image-approval proof from being reinterpreted as root-install authority. The plan itself is not a signature issuer.

The plan's proposed policy must match `NativeCatalogHost.enforce_installed_production_trust`: root-owned immutable module digests, exact source SHA, the existing root worker, pinned native Docker helper, immutable recovery service/timer definitions, original global Owner allowlist, explicit root readback controls and a running recovery timer. No broad root allowlist or production source replacement is permitted.

**Important hardening:** Both trusted-root preflight paths now explicitly execute the separately pinned, root-owned native deployment helper in the immutable catalog bundle. The ordinary read-only operator CLI may still use the existing live helper. Root must never execute mutable live source as a privileged helper.

## Mandatory production authorization boundaries

1. **Exact root installer authorization, not yet granted.** A root-owned installation transaction must independently validate a fresh cryptographic Owner approval binding the protected source SHA, exact root installation scope digest, existing root-worker rollback digest, original freeze SHA and manifest. A chat assertion by itself and an unsigned plan are insufficient. No standing permission or new Owner-wide allowlist may be issued.
2. **Root install and verification.** After that separate exact approval, preserve the original root worker, atomically install reviewed root-owned files, preserve native Release Manager behavior, install and activate bounded recovery, read back root policy/file digests, health, old live containers and freeze; rollback root files and service state on failure. The source-only plan is **not** itself a privileged installer or an issued approval.
3. **Distinct runtime/MCP image-promotion approval.** Stage the catalog scoped offer through the verified root worker, obtain a separately authenticated one-use Owner signed decision, promote exactly two pinned images, verify health, protected services and original freeze, with paired rollback on any failure. Do not expand Owner impersonation or replace protected PMv4/Ticket Core work.
4. **Separate provider write acceptance.** After the production service-identity switch is verified, separately authorize one inactive/nonbillable Autotask catalog service creation, provider readback and no-impersonation evidence. Only then proceed to the larger managed services/bundles catalog and verify each object.

## Test and remaining dependencies

Read-only plan tests cover exact path and policy allowlists, current Git-source binding, unchanged host/freeze, two independent release permissions, removal of any fake approval field, and denial of arbitrary/unreviewed paths or untrusted source. Root preflight regression verifies the independently pinned helper is supplied to both root paths. The utility never writes production state or contacts Autotask.

**Installation is still blocked** because there is no separately issued authenticated exact-action root-install approval or currently installed privileged root transaction for this catalog scope. This source package prepares evidence but does not pretend a command that can mutate root exists in the current runtime. A future root installer transaction must be independently completed and verified under a distinct exact Owner approval before a live provider test. Source-only work may continue without asking the Owner to perform manual engineering.
