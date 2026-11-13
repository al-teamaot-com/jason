# IT Glue read AppRole recovery — source-neutral release ancestry (2026-11-12)

**Engineering-only ancestry bridge; not production authority.** This file documents why a reviewed earlier production snapshot is recorded as a parent of protected-main history while leaving the current protected-main source unchanged.

- Running production and rollback baseline: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Exact proposed isolated release snapshot: `608c55419dbb4e2083c91cc08f04406c4bcda17e`.
- Immutable source Git tree: `66059951edeb07cc45e2125cca7a4e8dbf913523`.
- Comparison to running production: six files only, binary diff SHA-256 `2c4b6b0fb9f5067620c7320f1adfb713699e7573e25c90bfcbfcb4d8ee4d7aa4`.
- The same source was reviewed in #2461, passed 59 focused local tests and source-security checks. Only its read recovery helper, root-only inert installer, host reconciliation stanza, documentation, and their tests are included. No unrelated PMv4 owner issuer, Constant Contact OAuth, or full-SQLite recovery changes exist in the proposed release tree.
- Snapshot PR #2467 **must never be directly merged** into protected main: it would revert newer unrelated engineering source. Its purpose is to collect independent CI on the exact release revision.
- The ancestry bridge is constructed from protected main, with a deliberate `git merge -s ours --no-ff` to record snapshot as a second parent without changing protected-main source. This independent document is the sole intended net change. Before merging the bridge, reviewers must independently prove its final tree differs from the then-current protected main only by this document, and its exact snapshot parent is present.
- Merge of this ancestry bridge must obey protected-main policy, CI, independent security review and no auto-deploy. A merged branch merely makes snapshot reachable via the native release manager's existing `verify_candidate_on_main` check. If snapshot CI or branch checks fail, the release must not proceed.
- Following approved ancestry, produce a new native candidate for snapshot SHA `608c55419dbb4e2083c91cc08f04406c4bcda17e` with a current production rollback, immutable image and MCP digests, complete preproduction/negative tests, host reconciliation and freeze evidence. Explicit authenticated Owner exact-SHA production approval remains separately mandatory, including a complete scope disclosure.
- Deployment of the helper does **not** repair IT Glue automatically. Actual read AppRole SecretID recovery requires a further local authenticated `al` Owner approval, hidden OpenBao administrator password, bounded runtime credential refresh and independent governed IT Glue read acceptance. Provider writes remain separately disabled, pending dedicated write-key provisioning, validated disposable organization and exact-action create/update tests.

**No change to any production container, OpenBao identity, provider API key, client mapping or IT Glue record is authorized by this ancestry note.**
