# PMv4 — Stage A/B/D governed installation and acceptance packet

**Status:** November 12, 2026, SOURCE-ONLY engineering. Not a production release,
standing Owner approval, root control change, or completed operational cutover.
Use the exact final approved protected-main commit, live protected root readbacks,
and independent native release manager. Never execute the preproduction tools
directly against live services to bypass the protected breaker.

## Existing authority reused; no second signer or approval system

The currently deployed Jason MCP already authenticates Entra Owner sessions and
provisions the existing short-lived exact-release Ed25519 signer:
`/var/lib/jason/runtime-secrets/owner-release/private_key`, mounted read-only as
`/run/jason-secrets/owner-release/private_key` for the unprivileged MCP service.
The separately root-owned public trust pin is
`/etc/jason-owner-release/verified-owner-public-key.json`. PMv4 shadow issuer
and root controller reuse this exact trust chain, not a newly generated key.

`jason_mcp.server.EntraTokenVerifier.verify_signed_claims` invokes the same
JWKS-backed RS256/token-time/issuer/audience validation as ordinary MCP
authentication. The PMv4 Owner tool is **disabled by default** in
`config/pmv4-owner-issuer-activation.json`. Activation requires a reviewed
source profile, signed exact Owner session and matching current protected-main
candidate, rollback SHA, scope hash, manifest hash and freeze hash. No Teams
card is a required authority gate. The MCP issuer performs a public exact
protected-main HEAD precheck; the trusted root host independently re-verifies
the full protected-main and required CI, immutable rollback, root freeze,
breaker, hardware/container health, and host transaction locks before change.

The existing `deploy_live_container.py` now has an **allowlisted**, never
generic PMv4 projection for `jason-mcp-pilot` only. It projects the
root-owned PMv4 shadow tree read-only, plus only the child
`control/signed-owner-decisions` as writable to UID 1000/GID 1000 and the
root-approved Entra audience as read-only. All source directories, the
dedicated receipt subdirectory and root-owned audience file require strict
non-symlink UID/GID/mode and exact client-audience checks. No PMv3 state or
provider credential directory is introduced by this projection. Default OFF
preserves the existing MCP runtime. An exact MCP rollback forces the issuer
OFF and removes the three fixed mounts, including the writable receipt mount.

## Stage A — Install independent trusted host release/recovery

Prerequisites:
1. Approved and tested exact protected-main source, reviewed path digest,
   verified protected CI and a separate authenticated Owner release decision.
2. Protected release breaker closed by its **existing root-governed** recovery
   mechanism, with three distinct clean root observations and readback. Drift
   PASS alone is not permission to close it.
3. Fresh production source/health/holds/freeze/root readback, zero in-flight
   conflicting host release transaction and immutable rollback evidence.
4. An explicitly authorized, root-run installer under the **existing** native
   host release boundary (not a direct unprivileged script, self-issued key
   or manual modification of protected state).

Trusted host package:
- `tools/pmv4_host_install_contract.py` inventories and hashes the exact
  source modules. It supports **read-only inspection**, offline staging in
  a new temporary directory, tamper detection, and verified removal back to
  an **empty initial baseline**. It has no production `apply` command.
- Trusted root code is installed only under
  `/usr/local/lib/jason/pmv4-trusted`, root-owned and immutable by the
  native exact release transaction. Root PMv4 host lock:
  `/var/lib/jason/pmv4-shadow/control/host-mutation.lock`, UID 0 mode 0600.
  The existing PMv3 transaction lock must be held simultaneously.
- Host-installed shadow state under `/var/lib/jason/pmv4-shadow`: root owner,
  group 1000, parent/control/release/receipt dirs traversable but not
  group-writable; only `control/signed-owner-decisions` root:1000 mode 0770
  is writable by the existing authenticated MCP service. Entra audience
  `/etc/jason/pmv4-shadow/entra-audience.json` and parent are root:1000,
  non-group-writable and audience file group-readable, matching the current
  MCP Entra client ID.
- The existing signer/private key and root trust pin MUST NOT be duplicated,
  rewritten, moved or regenerated during installation.
- First shadow rollback SHA is forty zeroes, meaning **no prior shadow
  runtime**. Do not use an old `jason-runtime` image as this rollback.
- A new independent root shadow activation is permitted only after the root
  controller loads an already signed Owner proof. It then rechecks all host
  gates, deploys only the disconnected shadow namespace, records immutable
  receipts, and either verifies health or restores the exact absence baseline.

Offline acceptance: the temporary bundle is hash-audited, rejects edits,
untrusted modes, links and extra files, and restores a zero baseline without
touching other data. This is NOT root installation/readback acceptance.
**No Stage A production deployment occurred in this source-only work.**

## Stage B — Lock-aware embedded Ticket Core bootstrap

Before starting any external worker, exact-Owner-authorized release B upgrades
the *existing embedded* runtime so the actual ticket dispatcher child owns
`autonomy-operational-work.sqlite3.owner.lock` for its full lifetime, before
runtime construction, using the same durable file and inode as the future
external worker. The HTTP/supervisor parent is deliberately not the lock
owner: a surviving orphan child cannot silently lose the lock when its
parent exits. The legacy live worker (without lock) must have exited before
this protected runtime replacement. Do not delete the lock inode.

Verify the live embedded worker is the only owner; separate real scheduled
ticket scans, Autotask/DRMM provider readback, durable ledger and approval
receipt continuation, zero duplicate claims/notes/jobs, notification outbox,
MCP health and unchanged protected freeze. If acceptance fails, reconcile
in-flight work and restore the *verified original* source/image
`690250b4d21f32cce79cab9f5b4c18cf93e7e94a` using the native
transaction (or the authoritative newer LKG if it changed at release time).
Do not activate an external worker as a fallback. Real provider-backed
post-cutover acceptance remains separately required for Stage C.

Offline acceptance: child-owned lock, competing child denied before runtime
construction, existing supervised runtime composition and no duplicate
parent ownership. The GitHub CI Docker test runs three synthetic scan cycles
and one unique ticket claim on a private runner with no providers, production
state or secrets. Offline PASS is not a substitute for real service readback.

## Stage D — Independent JSON Runbook Management

Reuse the existing `SQLitePlaybookRegistry`, authenticated MCP JSON admin,
capability policy and audit ledger; no second registry or Owner role. Ordinary
runbook stage, activate, version and retire operations do not require PMv3
engineering/release tasks. The disposable six-process acceptance proves
immutable versioning, transactional receipts, generation tracking, retirement
and durable SQLite readback; GitHub CI separately runs each in an offline,
non-root, no-network container.

A separately hosted production Runbook Management control-plane lifecycle
is **NOT YET INSTALLED**. Do not claim service independence merely because
the data operations and synthetic processes work. The governed component
release must preserve the one authoritative registry, hot-read semantics,
existing Entra/Owner authorization and ability to continue while PM
engineering/release is intentionally unavailable. Only then replace the
MCP-hosted management lifecycle, verify real systemd/container supervision,
verify rollback and publish active System Registry readback. Existing
Markdown/code playbooks remain until each is safely migrated individually.

## Root hard boundaries and sequence

- Stage A before any host release/promotion; separately authorized.
- Stage B embedded lock upgrade before Stage C external worker.
- Stage D independent lifecycle only after separate deployment package and
  its exact Owner review; no coupling to Stage B application restarts.
- Production freeze, Owner pause, automatic-promotion hold, breaker and
  protected desired-state remain in force until separately authorized.
- No code in this packet installs a root signer, approves itself, restarts
  existing services, launches an external provider worker or retires PMv3.

**Cutover decision state:** Await governed root revalidation and exact release
authorization; do not treat a draft PR or passing CI as that authorization.
