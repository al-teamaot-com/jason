# Constant Contact — 2026-11-12 source integration and independent release review

**Scope:** Source-only development on the existing Constant Contact feature branch; no
provider credential changes, OAuth callback registration, production merge, ticket-worker
maintenance, provider POST, campaign, Teams approval bypass, or freeze change.

## Delivered in this development candidate

1. **ChatGPT / Jason attachment handoff.** Three new MCP entrypoints reuse the authenticated Entra identity, original universal plan issuer and existing runtime service. The preview accepts original XLSX bytes as base64, a caller-provided attachment reference, filename, SHA-256 and exact target list IDs. Original bytes are hashed locally; the source digest is stored in the encrypted work record and bound to the subsequent canonical import-plan arguments. A caller-provided reference is metadata, **not independent attachment authenticity or marketing consent**. Preview requires active AOT identity and contact-read permission before any provider access. Approval issuance uses the existing signed universal plan ledger; ordinary chat text is not accepted as authority. Import dispatch remains exclusively in the native Central Orchestrator prepared-execution path.
2. **Spreadsheet safety.** One worksheet, strict approved headers, up to 25 consent-evidenced pilot rows, no formulas, known rejected rows or unknown headings. Bounded ZIP count, inflate ratio, total uncompressed bytes, traversal, embedded content and external relationships. Preview never sends contacts or campaigns.
3. **Independent GET-only reconciliation.** New source-only tools/constant_contact_reconcile_once.py one-shot entrypoint and runtime-composed readback worker. The worker never calls the write dispatcher. It scans past unrelated/unsubmitted/verified rows, logs safe aggregated outcomes and stores exact immutable successful readbacks or confirmed provider-declared failures. Ambiguous POSTs remain claimed and cannot be resent; pending/unknown provider failures remain retryable as read-only GETs. Historical readback no longer requires an unexpired write approval issuer.
4. **Failure regression tests.** Positive authenticated MCP routing, pilot-inactive denial, original file mismatch, wrong type, malformed formulas, ZIP bomb and external link, absent consent, 26-contact pilot, duplicates, denied identity, cross-requester readback, transient provider readback failure, late dispatched row, unknown outcome and terminal failure durability.
5. **Branch reconciliation.** Feature branch includes the previously separate authorization-hardening PR #2439. The current source candidate branches from the merged feature head. Do not re-cherry-pick the security patch. A merge-tree dry-run against current protected main must be re-run at final promotion.

## Explicit boundaries and known gaps

- The MCP tool accepts original workbook bytes, but the **real ChatGPT attachment-to-MCP serialization path has not been provider-live tested**. A client may be constrained by the tool request payload limit. No fallback to reconstructed rows or fake hashes.
- Readback one-shot entrypoint is **source-wired, not scheduled**. A separately supervised systemd timer/service may be proposed after independent deployment review. Never install a timer or run an active loop as part of this source task.
- Source test success cannot substitute for authenticated Owner approvals, real AOT OAuth account binding, verified list permission/consent, actual post-activity readback or production health.
- There is no autonomous retry of ambiguous import POSTs. Unknown result requires operator reconciliation.
- The source comparison is not a release authorization; production freeze and ticket worker remain unchanged.

## Review gates before any provider contact or production deployment

- Run targeted Constant Contact connector, runtime, orchestration, and MCP suites, plus wider repository CI and secure source review. Confirm actual GitHub checks on the exact final source SHA.
- Reconcile final merge against the then-current protected main, including overlapping MCP, composition, approval and security changes. Review archive limits, identity assurance, source provenance, encrypted retention and terminal-state durability.
- Build a clean immutable production candidate and calculate exact candidate SHA and reviewed file-manifest SHA-256. Separately verify the **current protected production last-known-good rollback SHA**, freeze/breaker and production health via authoritative host evidence; do not infer rollback from branch history.
- Arrange an approved independent one-shot readback scheduler with no ticket-worker overlap and an explicit initial *disabled* profile.
- After exact independent Owner release authorization: register OAuth callback, securely provision secret locally via existing OpenBao prompts, verify AOT account/list identity, import 1–3 consent-backed test contacts, audit activity/readback and compare ticket processing before/after. Roll back and restore freeze if acceptance fails.

**No Owner action is needed for source-only engineering.**

## Source-only verification on November 12, 2026

- Reconciled feature branch includes security hardening and requester preauthorization.
- Synthetic/provider-fake, connector, orchestration, runtime composition and authenticated MCP interface regressions were run on the Jason host in isolated dependency paths. Baseline complete run: **210 passed**; two additional authorization/source-hash assertions passed in a targeted rerun. GitHub CI on the final pushed head is still required.
- The protected-main merge-tree dry-run was conflict-free against commit 07a7e58fc28efff076c46f2948814aea113ba6e5. Re-run on the final staged source SHA and re-check main advancement before promotion.
- The standalone reconciler --check-only returned profile_configured=false and executed=false.
- No verified live-provider acceptance, Owner credential staging, or protected production rollback evidence is asserted.
