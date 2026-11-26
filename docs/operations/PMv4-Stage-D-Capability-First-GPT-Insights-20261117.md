# PMv4 Stage D — Capability-first, just-in-time composition (Owner decision 2026-11-17)

**Status:** Source-only acceptance candidate; no production change, live JSON activation, provider write or new execution authority.

## Standing PMv4 development rule

Before engineering new code, J-Man/J-Dev must enumerate the existing System Registry and governed capability catalog. Classify the objective as:

1. **Compose** existing registered capabilities with a versioned declarative JSON runbook and existing policy.
2. **Extend** one genuinely missing reusable capability, preserving backwards compatibility.
3. **Build** a new primitive only after verifying that no existing capability or configuration can meet the exact requirement.

Document the capability reuse decision in the existing work record. Do not add a parallel scheduler, registry, approval plane, identity, API connector, or release mechanism. Normal configuration activation requires no rebuild or unrelated service restart once Stage D is operational, but it never grants permissions.

## Minimum implementation delta in the existing interpreter

The existing `JsonPlaybookInterpreter` now accepts explicit `{"$fact":"ticket_id"}` references within step arguments, including bounded nested dictionaries and lists. The caller supplies evidence facts from the already-governed work context. Unknown facts, ambiguous mixed `$fact` references and excessive nesting fail closed. It is intentionally **not** an expression evaluator or provider executor. String interpolation, dynamic URLs, commands and direct provider calls are not supported.

This is **one** instruction-construction improvement, not the full production composition engine. The governed worker must still bind preceding **verified** results to named facts; perform live capability schema/identity/approval checks; manage durable step progress, retry, and readback; and call only Central Orchestrator. No workflow JSON or model output can create its own privilege or prove a previous action succeeded.

## First acceptance case: GPT Insights

Reuse the existing `gpt_insights_tech_assist@0.2.1` evidence renderer, fingerprint/managed-note logic, and provider capabilities; preserve its currently documented Help Desk I / New / non-Recurring limitations until a separately versioned and authorized scope revision.

The Owner's newer desired end state covers all technician-facing queues excluding Copy/Print, internal-only non-noisy insights, independent remediation where separately authorized, verified same-company device linking, and useful subsequent Teams notices (not initial notices). This **cannot** be silently substituted into 0.2.1; record exact changes and approve the new scope/version before activation.

Acceptance sequence:
1. Shadow-only synthetic ticket and existing-note snapshots; exclude Copy/Print and recurring cases.
2. Read ticket, notes, CI/device and bounded same-client evidence through existing registered read operations.
3. Bind ticket/note identifiers from *verified* prior results to subsequent instruction arguments; never invent IDs.
4. Render advisory evidence and compare the persisted material fingerprint.
5. Under a controlled production acceptance with exact standing authority, create a single Jason-owned internal note only when absent, or update that note only when material facts change. Do not overwrite technician/client/workflow notes.
6. Prove unchanged input causes zero writes; denied/mismatched scope, missing facts and unauthorized write cause no provider mutation.
7. Verify authoritative Autotask note visibility/ownership/ID/body readback and mutation audit; separately confirm no client note, unwanted status/queue change, duplicate, or endpoint action.
8. Verify two real ticket scans and protected Ticket Core continuity before calling the workflow operational.

## Stage D and release boundaries

Do not deploy a second Runbook Management service. Complete existing Stage D registry schema migration, independent control-plane hosting, hot-read and rollback under the already specified governed release. Current production registry remains generation 0 with no active JSON playbooks per the last source-backed read-only verification; no new definition is activated by this change.

The source-only change and tests may be reviewed/merged under ordinary engineering authority if CI and governance permit; **production release**, policy/approval changes, live GPT Insights mutations and Ticket Core changes remain separately controlled. Do not use the deployed historical `list_json_playbooks` path as a non-mutating health probe until its documented read-only fix is deployed.

## Completion evidence

This document records a standing methodology and the bounded Stage D source delta only. The full objective remains incomplete until the existing registered capabilities can be selected, wired, governed, invoked and verified end-to-end for the GPT Insights pilot without new application deployments for each workflow.
