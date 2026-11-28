# Configurable rollback retention

Owner direction (JES-008, 2026-11-27): use configuration and established
records, not per-release cleanup scripts.

The existing native manager entrypoint has a typed rollback-retention operation.
It takes an already reviewed coordinated release ID, derives the needed slots
from its validated manifest and the live protected desired-state limit, and
uses `config/operations/rollback-retention-v1.json` to select only the
minimum number of eligible historical containers. Policy parameters are data,
not incident-specific code. Invalid/missing configuration fails closed; policy
cannot grant itself production authority or increase the native capacity limit.
The archival policy is unchanged; the separately authenticated reservation
operation below is the only new capacity path.

A historical container must be stopped, old enough, an ordinary timestamped
rollback of a supported service, and have an independently retained same-image,
same-source sibling with equivalent host configuration and bind mounts.
The reviewed policy may permit differences in the saved environment or
image-tag spelling only when the exact original configuration and complete
bounded root filesystem are archived in root-private custody. This does not
make the two original containers identical. A retained sibling and archive do
not restore the removed Docker container ID. Named volumes, recent, unique,
scoped and audit rollback originals are excluded. Active rollback references
deny retirement; accepted audit inventory history is preserved unchanged.

Preflight is read-only with respect to production containers, data, configuration
and authorization. It refreshes only the existing trusted source cache. It
binds actual inventory and IDs, every selected exact original and sibling,
reviewed source/configuration, protected release manifest, root policy,
protected peers and incident hold into one authenticated Owner scope.
Execution reuses the existing Owner verifier and shared production locks.
A root-private approval record and independently readable checksummed archive
must exist before exact non-force removal. No image, volume, bind-mounted
data, live peer, freeze setting, provider write or automatic promotion is
authorized. Native capacity and independent live health must pass afterward.
Root-private receipt records provide exact-scope continuation and verify
an interrupted removal without selecting another target or minting authority.
Never report rollback retention complete from a source-only merge.

The older audit-journal exact historical archival helper is not changed;
its previous pinned bytes and immutable approval evidence remain intact.

## Capacity lifecycle and reservation

Before staging any reviewed release, use the existing native manager entrypoint
with `--rollback-retention --release-id <reviewed-release-id> --assess-capacity`.
This read-only assessment reports the effective limit, occupied/available slots,
release demand and eligible duplicates without exposing saved container environments.
It distinguishes capacity available, duplicate archival available, bounded
reservation review required and a genuine policy-ceiling blocker. A suggested
reservation is not storage admission or authorization.

If duplicate archival cannot meet the reviewed demand, the separate
`--reserve-capacity` mode derives the minimum exact increase from live inventory
and the offer. `config/operations/rollback-capacity-reservation-v1.json` bounds
this operation (initial ceiling 29, at most two additional slots per transaction,
10 GiB minimum free space on both the Docker and archive filesystems). It uses
the same protected-source and CI checks, Owner verifier, release locks, pending
transaction checks, atomic replacement, protected live component readback and
native release admission. Only the stopped rollback container capacity field
in the root-owned effective desired-state policy and its exact dependent
`file_sha256.desired_state` controller pin may change. All existing
containers, images, volumes, data and unrelated settings remain intact.

The exact preflight binds both files' before/after hashes, full normalized
inventory digest, reviewed manifest, source and configuration. `--apply` requires
the exact preflight scope SHA and authenticated Owner decision. An immutable
root-private receipt and both before-images precede the change. Afterward the full installed
controller policy verifier, existing native gate and independent production drift evaluator must pass, and the same
inventory and protected peers must be observed. Otherwise both exact before-images
are restored. `--resume` accepts only an unresolved, still-valid exact approval
and matching before/after images; if interrupted between the two writes, it
first restores the approved pair under native locks. A completed operation
cannot be replayed.

Legacy reservations with a successful immutable receipt but no approved
controller pin update require a separate `--reconcile-capacity-binding
--reservation-source <approved-reservation-source-sha>` exact Owner decision.
It accepts only the previously approved capacity before/after bytes, unchanged
inventory/protected peers, a terminal preceding release and a single stale
controller pin; every unrelated installed hash and reader binding must match.
It changes only that dependent pin, then runs the full native installed-policy
verifier and independent drift guard. Prior receipts and the effective capacity
policy remain unchanged; no application release is approved by this operation.

If the stale legacy pin already caused the scheduled recovery service to fail,
`--recover-binding-fault` adds an explicit maintenance-only scope. It accepts
only the root-recorded failed recovery service fault, its exact current
systemd invocation error and the derived pinned watchdog failure, with fresh
independent evaluation, immutable LKG, all prior evidence and no pending
transaction. It never waives an unrelated fault or changes release admission.
After verifying the exact repaired pin, release the native locks, run the
existing recovery and drift watchdog one-shots and use the existing native
root breaker revalidation. The breaker must independently close and the final
normal native gate and exact scope must pass. If revalidation is interrupted,
retain the verified binding and continue the original approved scope; do not
write a success receipt or reintroduce the known stale pin. No application
containers, rollback artifacts, freeze, or Owner approval records are changed.
The release itself still requires its own approval.

The 29-slot ceiling is a bounded headroom decision, not an indefinite increase
or permission to delete unique rollback identities. Future exhaustion must first
be assessed using the existing lifecycle; no automatic ceiling escalation.
Any future archive-and-retire policy for unique originals must prove recoverability
and preserve active rollback references before retirement is admitted. Do not
claim restoration of an original Docker container ID from a filesystem archive.
