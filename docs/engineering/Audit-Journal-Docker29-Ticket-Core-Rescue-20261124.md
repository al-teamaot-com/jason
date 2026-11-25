# P0: Restore ticket-core after Docker 29 default-value normalization blocked journal rollback

**Status:** Source only. No production Docker API write is performed by creating or merging this code.

## Production incident

On 2026-11-24 06:58 EST, the previously authenticated one-use Owner recovery `FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL` completed Root preflight and put the hardened systemd CAP_SETUID correction into production. The journal writer UID1000 read succeeded, the release drained work, and its first Docker consumer replacement attempted `jason-pmv4-ticket-core`. The native executor correctly refused `AUDIT_RELEASE_UNKNOWN_REPLACEMENT_CONFIGURATION` at container/create readback, entered its exact approved rollback path, but hit the same comparison error on the recreated original container. Native systemd auto-restarts are exhausted.

The canonical SQLite remains legacy, live and unchanged in device/inode, and the archive is empty. `jason-runtime` and `jason-mcp-pilot` are still running. `jason-pmv4-ticket-core` is a *Created*, not Running, Docker container; the original stopped before-image and the dormant planned container are separately retained. The journal release unit is failed and its maintenance timer disabled. **Service restoration is the immediate priority; this is not an accepted cutover.**

Read-only comparison of real Docker Engine 29 API snapshots against the exact trusted original Root image showed a single discrepancy: the original `HostConfig.OomKillDisable` is JSON null, while the created container's effective default is `false`. Every other original-config key, HostConfig key, mount, port, network and image matches; the dormant planned container has the same single normalization difference against its reviewed planned body. No secret env value is printed or altered.

## Reviewable source fix

`tools/audit_journal_container_release.py` now recognizes **only** this exact direction of Docker normalization: expected `OomKillDisable=None`, readback `OomKillDisable=False`. It does not treat the opposite transition as safe. Every other privilege, security option, namespace, mount, image, network, port, configuration and resource field retains exact matching. The installed Root trusted copy is **not** patched by this PR; the code fix must be separately deployed through reviewed governance before any subsequent journal migration attempt.

## Immediate governed one-use rescue

`tools/audit_journal_install.py --rescue-exact-ticket-core` stages only reviewed protected-Main sources, verifies exact Git checkout and custody, protected Main CI and native audit-journal migration acceptance CI, then calls `tools/audit_journal_ticket_core_rescue.py` under existing Root operator locks.

The new Root-only helper insists on:
- the exact already Owner-attested failed journal candidate `20b32548402d160f9c6a5ee33a0a17592eb9fa68` and latest failed scope `ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3`;
- immutable Root Owner, plan, adoption, installed trusted-source code and before snapshot consistency; only the original ticket-core install and restoration steps, both incomplete, no other consumer attempted;
- a stopped failed journal release, disabled timer, original legacy SQLite device/inode, empty archive and unmodified global security baselines;
- exact original stopped backup and dormant created backup identities, and the current Created ticket-core with full verified original body (only nullable OOM normalization permitted);
- both runtime and MCP consumers still running with original IDs/configurations, original Root policy SHA and open breaker;
- **fresh independently verified licensed Owner authentication** through the existing pinned Entra verifier, with a new unique exact-action string, source SHA, rollback SHA, exact current container ID, and scope hash. It rejects unrelated Owner identity or expired/consumed action.

Following fresh Owner consent, recheck the entire exact current scope, persist a private Root one-use authorization before any Docker mutation, then perform exactly one Docker API `POST /containers/<pinned existing Created ID>/start`. It **never creates, renames, removes, updates, or stops a container**, never starts the journal release service, never changes SQLite or audit Root receipts, never clears the breaker, and never reuses the previous migration consent. It verifies that the original configuration is running and healthy; if the Docker response is ambiguous, it only reads back once and does not issue a second write. The original rollback backups remain intact.

This is a narrowly scoped reusable governed interrupted-container safety workflow, **not an ad hoc Docker CLI workaround** and not acceptance of the journal migration.

## Acceptance

1. Current Root preflight and scope checksum PASS; Entra Owner identity verified and exact action approved.
2. One-use protected Root evidence `authorization.json` plus `result.json`, no extraneous Docker API writes.
3. `jason-pmv4-ticket-core` runs with pinned original image and exact original configuration, original rollback backups untouched, `jason-runtime` and `jason-mcp-pilot` remain running; ticket processing returns to healthy state.
4. Audit release remains failed/quiesced, catalog remains legacy and all existing evidence retained. A separate **reviewed and freshly approved** journal rollback-code reconciliation must occur before the migration is resumed; do not start the old code against the stopped/recovered container.
5. Only after full journal rollforward, parity, restore, scheduled maintenance, native drift/breaker closure and root disk reclamation can the overall user objective be reported complete.

Regression tests include original/dormant real Docker read-only parity, nullable OOM default vs inverse and all security-field denials, wrong Owner, altered IDs/images/mounts/journal, single exact POST, receipt evidence, transport loss without retries. Full repository CI/SEC-007 required before production.
