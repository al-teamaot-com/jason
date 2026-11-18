# PMv4 Stage E — provider-free generic release canary and scheduling

Status: SOURCE ONLY, not a production release or PMv3 retirement.
Issue: #2577. Accepted baselines: Stage C Ticket Core, Stage D Runbook,
A1 v5 disconnected shadow, current production freeze, native drift PASS.

## Why a separate canary?

Installed generic independent controller source is commit
675b99e73c33c228a8531c2797eb3db53c399ad8.
Its installed core SHA-256 1e6f981344f6fbb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7
and financial host adapter SHA-256
36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce
remain byte-identical. The separate financial-statement release explicitly
pins both, so they must not be changed for this canary.

Canary project jason-pmv4-e-canary, one service pmv4-e-canary.
Internal private Docker network jason-pmv4-e-canary-private only.
No published ports, no external or provider connection, no provider
credentials, no authority mounts, no writable mounts. One root-owned
read-only canary config from an exact SHA-owned release bundle is
mounted at /canary/config.json. Image: content-addressed accepted
preproduction A1 shadow image
sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd.
Effective memory target 128 MiB; PID cap 64; UID 1000; readonly
filesystem; drop all capabilities; no-new-privileges; no restart;
pull never.

The image provenance SHA label is the earlier accepted shadow commit
75f2b4c0c48a15bd17d700b9f039fe56623e3f52. The canary
candidate/source SHA is a distinct NEW protected-main source commit
containing the source Compose and config files. The immutable packet
attests both separately; it never lies about OCI/source agreement.
The Compose source uses a single exact whitelisted nonsecret variable
JASON_PMV4_E_CONFIG for its root-owned SHA-specific config mount.

## Existing controller and rollback evidence

The unchanged generic ComponentReleaseController is exercised in
an isolated simulated host with a real Ed25519 exact-action signature,
provider_scope none, exact prior-zero component rollback and unchanged
protected-service snapshots. A successful acceptance creates a
durable native receipt; duplicate promotion is rejected; failed
acceptance rolls back only the canary; failed rollback remains pending
and stops a fresh approval attempt. Source-only tests are NOT live
production parity.

tools/pmv4_e_canary_contract.py validates one exact Docker Compose
projection and image labels. tools/pmv4_e_canary_packet.py verifies
exact protected-main Git blobs, CI, immutable prior OCI image identity,
reviewed manifest/scope and frozen source SHA. It stages an unprivileged
source packet only; no Owner proof, Docker creation or provider action.
A distinct root-owned, SHA-pinned canary companion host callback and
exact Owner-outbox root entrypoint have been authored as source-only
tools/pmv4_e_canary_host.py and tools/pmv4_e_canary_release_root.py.
Their code reuses the installed original generic controller and its
original financial host adapter's host locks, freeze and protected
readback, and validates actual Docker isolation including private
network internal=true and exactly one peer. Neither module has been
root-installed. A separately Owner-approved immutable root bundle and
protected CI attestation are still required before live invocation.

## Replacement scheduling tests

tools/pmv4_e_scheduler_parity.py reuses the existing durable
pmv3_work_engine library, not a second task engine. Disposable
isolated state and one shared inode lock demonstrate a single claim,
receipt deduplication, idempotent crash resume in another process,
non-idempotent uncertain-work hold, missing Owner approval hold and
unknown/provider action denial. The source-only exact six-unit
retirement delta preserves protected runtime, MCP, boot, drift,
authority, provider canaries and client monitoring.

The old 3 user timers plus 2 root timers and 1 root path remain
installed, active and required by protected desired-state policy.
The replacement production engineering and release/approval schedules
have NOT yet been installed or accepted. These tests are preparatory
and must not be treated as source/production parity.

## Production NO-GO

The native production drift watchdog rejects undeclared running Docker
containers. Because the current protected policy has no canary allowance,
a live canary MUST be preceded by a separately approved exact protected
policy transition adding only the canonical Compose container name
jason-pmv4-e-canary-pmv4-e-canary-1. The source-only planner
tools/pmv4_e_canary_drift_policy.py verifies the original root policy
byte hash and generates the one-name allowance; it preserves all other
fields. On cleanup, stop and verify the canary absent BEFORE restoring
the old protected policy bytes; deny if the current protected policy
differs from the approved candidate. No watchdog suppression, general
container allowlist or breaker bypass.

Before a live canary: pin and install a root-owned canary host adapter
under separately reviewed exact Owner proof; generate root-owned
candidate bundle and protected CI evidence; verify all C/D/A1 root
receipts, protected host locks, freeze and closed breaker; obtain one
fresh authenticated Owner exact-action signature; perform one native
generic component release and bounded rollback, checking effective
network/resources, protected-service identities, audit and final
freeze. Do not substitute the financial SharePoint writer.

Before PMv3 retirement: prove actual engineering/approval/release
scheduler parity with old PMv3 jobs quiesced in an isolated host;
prepare one reviewed protected source/root old-new unit delta; obtain
fresh exact Owner retirement release; restore all old state on failure;
verify two separate real ticket scans, no duplicate claim, release and
recovery, root/security monitoring and no remaining PMv3-only paths.

This source-only work issues NO authorization and makes NO production
mutations. The production freeze stays unchanged.
