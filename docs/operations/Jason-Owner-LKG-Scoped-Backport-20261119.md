# Scoped Jason Owner-only candidate — source-only recovery engineering

This branch is descended directly from production's currently aligned last-known-good SHA `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. It is deliberately **not** an ordinary full-current-main release. The exact Owner authorization source was transplanted from reviewed and merged PR #2640. The expected active human Owner is `al@teamaot.com`, and the separate Microsoft administrator `al_admin@teamaot.com` is specifically denied Jason Owner authority by this opt-in source profile.

## Scope and verified baseline

Only the eight code/config/test files included in this branch's baseline diff are in scope: signed Entra Owner check in the MCP server, exact source profile declaration and parser, native release manager / MCP deploy source selection, and focused negative tests. This branch does **not** change production Ticket Core, runtime, JSON registry, Autotask data, Datto devices, Microsoft identities or shared release-manager state. Existing historical rollback environments still default to no new Owner authority.

The merged Owner source is on protected `main`, commit `61b9ce79316f6bf2eb9da9835ccf3f9015a6c71d`. This private backport is a separate candidate, not an authority grant. Native production admission requires additional independently checked exact release source pin, immutable candidate image digest and runtime/no-restart proof. The ordinary release manager must **not** treat this backport as a full main candidate by changing Git ancestry or bypassing protected-main policy; it requires a separately authorized scoped native release profile.

## Exact release requirements before any production mutation

1. All source and security tests pass against this LKG overlay, and any missing old test source is documented rather than silently imported from new main.
2. Build an isolated, network-disabled MCP candidate image with no provider credentials or writable production volumes. Runtime image must stay byte-identical to current LKG. Measure image IDs, diff and tests.
3. Independently verify four scoped-backport systemd units under their separate root-install and drift governance: read-only hashes match registered source, a one-use signed Owner action alone may authorize protected root inventory reconciliation, the watchdog must pass, and the breaker stays fail-closed until native revalidation.
4. Obtain exact signed, authenticated `al@teamaot.com` Owner decision for candidate/rollback/scope/manifest/freeze hashes, through an existing approved source-controlled release surface. Neither a verbal chat instruction nor GitHub merge equals a reusable signing receipt.
5. Native root promotion must use only the reviewed MCP candidate image, maintain the runtime and PMv4 ticket-core containers unchanged, preserve freeze and produce verified rollback before claiming success. Never deploy a diff of hundreds of unrelated files.
6. Postflight: Jason's Owner-status tool succeeds using the authenticated licensed Owner; the Microsoft admin identity cannot authorize a Jason action; no provider write occurred; both production images, runtime health, freeze and JSON registry remain as expected; a negative test must not consume a real approval.

**Current status:** Source-only LKG overlay, awaiting image build/rehearsal and separately signed root release approval. Not deployed.
