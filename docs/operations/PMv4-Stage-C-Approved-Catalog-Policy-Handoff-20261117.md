# Stage C: reuse root-accepted catalog policy during independent worker handoff

**Source-only. No production mutation, no Owner proof issued for this release.**

The earlier canonical Ticket Core cutover packet was pinned to the effective
production drift policy *before* the catalog-recovery-unit reconciliation.
That packet MUST NOT be reused. The catalog policy repair was separately
Owner-authenticated as action
`pmv4-catalog-four-unit-drift-policy-reconcile-v1`, source
`769d8cad698d092779def1dcfb8ba5e1fc896a9d`, and a root acceptance
receipt. Its resulting approved policy SHA256 is
`e17ffed6b6c4589721d69a46a25b80f80d571e8b67e1726c881647d07e29a2b8`.

The postmigration worker handoff builder now requires the exact original Stage C
policy and accepted four-unit catalog policy evidence; the root release
independently rechecks that immutable proof and its root-only acceptance
receipt before any mutation. It uses the accepted catalog policy as the
baseline. Its desired policy changes ONLY two keys:

- Adds the originally reviewed `jason-pmv4-ticket-core` container to the
  allowed running containers (retains all four catalog recovery units)
- Allows the single additional stopped rollback container (20 to 21)

All other drift protections, root freeze, MCP, runtime image, worker image,
canonical SQLite inode identities, and host release locks are unchanged.
Host-only synthetic policy evaluation returned PASS with zero problems.
Rollback must restore the *new accepted* catalog policy, never the pre-catalog
policy. Any missing root catalog acceptance, mismatch, changed main, signed
Owner plan, protected CI, or unrelated drift fails closed.

A new exact Entra Owner approval remains required for the runtime-hosting
cutover, followed by two genuine provider ticket scans, native drift
verification, unaltered MCP, and final signed acceptance receipt. Stage D and E
remain independent acceptance boundaries.
