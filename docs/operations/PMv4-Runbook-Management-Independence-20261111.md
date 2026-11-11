# PMv4 — Runbook management independent of the Production Manager

**Status:** Source-only, preproduction. Existing service and authority remain unchanged.
**Owner intent:** Runbook lifecycle must not wait for PMv3 engineering, releases, approvals, or Codex-capacity availability.

## Existing reusable capability

- `implementation/autonomous_remediation/playbook_store.py`: existing SQLite, WAL, immutable versioned JSON playbook registry.
- `implementation/mcp_service/src/jason_mcp/json_playbook_admin.py` and `server.py`: authenticated `validate_json_playbook`, `stage_json_playbook`, `list_json_playbooks`, `activate_json_playbook`, and `retire_json_playbook`.
- `playbook_document.py`: deterministic semantics and forbidden shell/direct-provider keys.
- Staging and activation do not mint provider authority. Owner identity, capability grants, autonomous promotion, audit, isolation, and approval requirements remain independently enforced.

**Observed on November 11, 2026:** The live JSON registry responded with generation 0, zero registered JSON playbooks. Existing production Markdown/code playbooks are NOT automatically equivalent to JSON definitions.

## Minimal source-only hardening here

The existing registry now uses one explicit SQLite `BEGIN IMMEDIATE` transaction for each stage, activate, or retire operation. Each real state change writes an actor/fingerprint/generation lifecycle receipt **in that same transaction**; a failed receipt aborts the registry change. Repeating an already applied lifecycle action does not create extra receipts or generations. Concurrent MCP clients share one SQLite file, not a PM queue or release transaction.

This fixes a concrete atomicity defect: the previous connection used `isolation_level=None`, so `with connection:` did not explicitly begin a transaction. Multi-statement activation could previously leave partially committed state if interrupted.

## Isolation contract / remaining work

1. **Independent control-plane endpoint:** Keep existing authenticated MCP JSON administration. It must remain available when PMv3 engineering, release queue, approvals, or associated timers are paused. Do not route changes through PM queues.
2. **Controlled configuration:** Convert old source-code-dependent runbooks incrementally to the existing JSON schema, with parity testing per runbook. Do not claim all current runbooks are already configuration-managed.
3. **No authority from configuration:** Activation only changes the registry. Any newly declared governed execution requires the existing independent exact capability/approval policy.
4. **Independent deployment:** Eventually package the Runbook Management control surface and registry separately from PMv4 and Ticket Core; do not restart or redeploy those components for ordinary version changes.
5. **Operational acceptance:** On a controlled sample (no real provider action), validate → stage → list → activate → verify generation/receipt/hot-read → retire → verify readback, while PM engineering is intentionally paused. Verify a failed activation rolls back atomically and that the ticket worker continues scanning.
6. **Rollback:** Retire a bad active version or reactivate the prior independently verified version using existing Owner authority and immutable receipts. Do not revert or delete execution audit.
7. **Live change boundary:** An actual production runtime rollout, new service packaging, activation of a real playbook, or authority policy change still requires the separately governed release or Owner action appropriate to that exact change.

This is intentionally not a second runbook database, new authorization system, replacement for the existing JSON engine, or automatic production rollout.
