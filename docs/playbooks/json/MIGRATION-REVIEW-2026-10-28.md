# Jason JSON playbook migration audit — October 28, 2026

## Scope of this change

**Documentation and review artifacts only.** This branch does not change `implementation/autonomous_remediation/playbook_registry.json`, runtime code, prompts, production queues, endpoint actions, grants, owner promotions, MCP control plane state, or release behavior. Do not merge it as a substitute for a production migration.

- [Machine-readable source registry status](./migration-status-2026-10-28.json): snapshot of the **16 entries** in the source registry, **14 production-classified** and **2 pilot-classified**; their autonomy declarations are *source metadata*, not live activation proof.
- [Windows Time candidate JSON v1](./candidates/windows_time_source-0.1.1-jsonpreview.json): a **disabled, unstaged, classification-only** data-model preview based on the existing pilot. It contains **no provider execution steps, no permission grants, and no remediation**.
- Authoritative runtime definition: [JSON Playbook Runtime](../Jason-JSON-Playbook-Runtime.md), with schema [playbook-v1.schema.json](./playbook-v1.schema.json).
- Authoritative human playbook: [Jason Windows Time Source Self-Heal](../Jason-Windows-Time-Source-Self-Heal.md).

## Current architecture findings

1. The existing source registry (`implementation/autonomous_remediation/playbook_registry.json`, schema version 2) is **not** the same format as the executable JSON v1 documents. Do not replace, concatenate, or bulk-import it.
2. The repository contains the JSON schema, semantic validation, immutable staging/activation store, MCP admin handlers, and `JsonPlaybookInterpreter`.
3. The inspected interpreter **returns instructions**; it does not invoke governed providers. Code-search evidence found its direct references in its module and unit tests, but no verified autonomous-ticket-worker integration. This must be proved independently before any production claim.
4. The JSON v1 validator forbids graph cycles, while operational playbooks commonly require repeated rechecks; reconcile this with the shared durable runtime before migrating a real waiting/retry loop. Do not work around it with an unbounded custom cycle or a fake one-shot completion.
5. The current interpreter passes declared `arguments` through unchanged. Safe binding of exact ticket/client/CI/device/alert IDs and validated evidence facts into selectors is a prerequisite for provider-facing JSON steps; do not put raw shell, PowerShell, arbitrary URLs, or untrusted runtime substitutions into documents.
6. Jason's live JSON staged/active registry and exact owner promotions were **not available for verification through the current ChatGPT Jason connector**. Snapshot status is source-only. The [October 28 control board](https://github.com/al-teamaot-com/jason/issues/526) reports production health requires revalidation; do not initiate an uncoordinated release.

## Acceptance sequence (do not skip)

1. Confirm the existing JSON validator can validate the preview on a non-production target and record its fingerprint, and run its deterministic branch tests.
2. Reconcile the exact authoritative capability catalogue and client-scoped argument-binding/evidence-fact contract. All mandatory facts must come from governed source reads, not user-supplied boolean claims.
3. Prove the JSON runtime's integration with the existing autonomous ticket worker or explicitly record that integration is missing. Reuse the existing work-start/CI/ownership/recheck/documentation and failure-contract boundaries, not a parallel scheduler.
4. Convert **one** complete low-risk existing playbook with no authorization expansion, preserve Markdown as source reference, and prove parity in a controlled **shadow/dry run**: trigger, correct identity, positive/negative evidence, branch decisions, stale/error paths, durable state, safe waiting, duplicate suppression, and correct terminal verification.
5. Only then separately review owner-bound activation and *any* autonomy scope changes through existing governance. A JSON definition, successful validation, staged document, or activated registry entry creates **no new execution authority**.
6. Do not bulk-convert the other 15 entries until first-pilot operational acceptance. Record each subsequent version with exact source/fingerprint, tested scope and independent production acceptance.

## Explicit limitations

The `windows_time_source` JSON preview intentionally **does not claim full feature parity** with its Markdown playbook. It maps deterministic human-review and healthy-evidence classification only. It does not collect Windows Time evidence, perform resync, clear the alert, update a ticket, or reliably schedule recurring rechecks. A `complete` instruction in this **disabled preview** is a *classification terminal*, not evidence that an alert or Autotask ticket has been closed. **Do not stage/activate this preview as a production playbook.**

## Separate operational knowledge improvements

The Riggins workstation investigation suggests reusable read-only checks for effective lock/idle policy, DNS/DC locator, and correlated network/event evidence. Add those as domain-specific diagnostics to the existing Windows Idle Log Off, DNS Agent, and connectivity/runbook documentation **under separate documentation-only changes**; do not introduce DNS-server remediations or shorten/remove security lock policy without exact client policy and approval.

## Review/closure

- Treat this branch as a **review-only** JSON authoring milestone.
- No production health, client ticket, automation component, or release outcome is changed here.
- No staging, activation, merge, deployment, or production acceptance is claimed.
- Next recommendation: make a focused JSON runtime/worker parity and selector-binding acceptance plan *after* the currently prioritized P0 production-manager / Teams work, then promote one bounded playbook migration.
