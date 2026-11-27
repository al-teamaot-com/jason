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

Current Teams scope needs three slots; live capacity is 25/27. The source
planner selected one oldest eligible MCP original with a newer same-image
sibling. Current exact execution must still pass native admission and Owner
authentication; archive and actual capacity have not been modified.
