# PMv4 Stage E approval bridge — source-only integration

## Observed problem

The installed Stage E bootstrap reads an exact, short-lived signed Owner
request from `owner-proof.json`. The previously approved candidate is
`510243494efcd592a1585c681a3fa28a29296e17`, with rollback
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. The last observed candidate
directory contains expired proof files and no current `owner-proof.json`.
The root bootstrap and its original native verifier remain the authority for
production admission.

The live host reconciler does not admit a Stage E action, and the connected
remote session runs as UID 1000. The available remote tool blocks sudo. Do not
repurpose another root action or weaken that boundary.

The existing exact candidate is an ancestor of protected main observed at
`fb1d5f57c57c3675896eb06ca88b236c7718d6e8`, but
`verify_pinned_candidate_against_main` denies it because newer protected
commits touch release controls and scope. The review must be repeated against
the advertised main head at execution time.

## This source slice

The new MCP adapter accepts a synthetic verified Entra bearer, exact reviewed
offer and one exact Owner decision, then reuses the existing Stage E
`signed_request` and native signer. It emits the existing bootstrap request
schema in an isolated test. It does not record a live decision or publish a
request. Production is denied by default and explicitly denied when requested.

The root bootstrap reports which reviewed artifact is missing rather than
returning an unclassified `FileNotFoundError`. It still rejects missing or
untrusted artifacts.

## Remaining work before any release

- Implement and independently review a Stage E-only root dispatcher with a
  root-owned allowlist and the existing native one-use signature and locks.
- Bind the MCP entry to the existing verified session, exact immutable offer,
  protected source and root readiness. Record the already granted Owner
  decision only when the approved scope is verified; do not represent a
  synthetic decision as live evidence.
- Reconcile newer protected source and dependencies, verify fresh CI and root
  preflight, and prepare a byte-exact release and rollback. Resolve any actual
  change in approved scope through the governing approval process.
- Install and verify the matching MCP and root components through an available
  governed root execution path; then perform Stage E and post-cutover checks.

No production release, root execution, approval consumption, or cutover is
claimed by this source slice.
