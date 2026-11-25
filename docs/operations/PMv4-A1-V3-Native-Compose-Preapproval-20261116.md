# PMv4 A1 v3 - Correct native Compose preflight before future Owner authentication

Status: Source-only corrective engineering. NOT deployed. NO new Owner consent.
Original production freeze, promotion hold, Ticket Core, MCP and watchdog unchanged.

## Confirmed cause of the failed signed A1 v2 release

Owner authenticated and signed action pmv4-a1-one-owner-exact-disconnected-shadow-bootstrap-v2,
source e187d4a8a33f46d718fe27815e999690cf5a6c98, approval
owner-mcp-1d28029e9de249e0b56a0e34288b4b84. Root validation
reported ShadowReleaseDenied:SHADOW_COMPOSE_DRIFT.

The native ShadowController.preflight always compared old root-installed
rollback Compose (SHA256 892f7a506fcb759887697f4a9882a76e2377969a701a4ca1aff240f6cb23277b,
root owned mode 0640) against the SHA256 of the new candidate Compose
(fa3a4da73b1b208822193b559c0f8c39ee13e1ebe92f1edb1fe2cdae1fc06dfb).
The two files are intentionally different. The adapter already selected
the new candidate for Docker up; the native admission code was stale.

Independent readback after failure: no new native receipt, no shadow
container, original 40-zero pointer, failed release source/manifest and
token absent. Root audit and authenticated v2 approval exist and are
consumed. Production runtime healthy, MCP running, drift PASS, freeze
and promotion hold unchanged. Never rerun that exact v2 approval.

## Scoped source correction

Native ShadowController adds opt-in compose_binding=candidate. It verifies
BOTH the original root-owned rollback Compose against a separately pinned
legacy SHA256 and the root-staged immutable candidate Compose against the
new signed manifest SHA256. Candidate mode also rejects an untrusted
inode, changed file mode, symlink, wrong hash, unsupported binding and
changes to the original rollback file. The default prior root binding
and native lifecycle acceptance tests remain unchanged.

The new source-only deterministic release generator assigns a distinct
v3 action, root audit journal and one-time staging location. It loads
native ShadowController from bytes independently SHA256-matched against
protected Git main. Dynamically loaded modules have registered identities
needed for Python dataclasses; their import-root file locations point
ONLY to the root-installed trusted A0 library, not the mutable archive.
Candidate source bytes must pass a separate manifest/Git hash check.

Before another Owner authentication request, the v3 root preflight must
verify the previous v2 root audit hash chain, exact previously used
Owner/source, terminal rolled_back without committed or requires_review,
original signed v2 proof, absence of v2 release artifacts, root ownership
and original SHA of protected rollback Compose, and exact archived
candidate Compose SHA using the SAME reviewed native helper. It then
checks source CI, 40-zero rollback baseline, root watchdog allowlist,
breaker, dual native release locks, Ticket Core/MCP and freeze/hold.

Historical v1 and v2 approvals cannot be reused. A new exact
one-use Owner decision may be obtained only after the new immutable
source/image/plan and privileged preflight independently pass.
No Teams approval is required.

## Source acceptance

Disposable native preflight tests verified different legacy/candidate
Compose files with a properly signed approval, failure of the old
comparison, tampered files and symlinks, bad hashes, and unchanged
rollback pointer and zero receipts. Dynamic source tests verify native
dataclass import, source tamper denial, module namespace collision,
root-trusted Python import path and pre-Owner check ordering.
The integrated source suite passes 160 tests and 39 subtests.

The following are NOT proven by source tests: the actual privileged
v2 root rollback journal, new merged-main SHA, new offline OCI label
and immutable release packet, privileged preflight, live network-
disconnected gateway health, and native signed end-to-end rollback.
No production deployment is claimed.
