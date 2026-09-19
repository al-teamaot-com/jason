# Jason AI Security Triage

## Section Goal

Provide one bounded, reusable AI decision-support layer for security-oriented playbooks so Jason can evaluate governed incident evidence as benign, suspicious, threatening, or inconclusive without turning model judgment into execution authority.

## Prompt and implementation

- Prompt ID: `PROMPT-SEC-001`
- Version: `1.0.0`
- Lifecycle: `pilot`
- Source: `implementation/orchestrator/security_triage.py`
- Evaluator: `SecurityTriageEvaluator`

The evaluator receives only caller-supplied governed evidence plus optional standing-policy context. It receives no connector handles, provider credentials, action tools, or execution authority.

## Output contract

Allowed classifications:

- `benign`
- `likely_benign`
- `suspicious`
- `likely_threat`
- `confirmed_threat`
- `inconclusive`

The structured result also requires:

- confidence band;
- cited threat-evidence references;
- cited benign-evidence references;
- material missing evidence;
- recommended next evidence/workflow step;
- human-review requirement; and
- concise reasoning summary.

## Deterministic safety rules

Model output is validated after generation. Jason rejects:

- evidence references not present in the supplied governed evidence set;
- duplicate evidence references;
- `confirmed_threat` without cited threat evidence;
- `benign` without affirmative cited benign evidence;
- `confirmed_threat`, `likely_threat`, `suspicious`, or `inconclusive` with `human_review_required=false`;
- malformed output or missing required narrative fields.

A triage result is evidence/decision support only. It cannot authorize a provider action, modify a system, close an Autotask ticket, clear a DRMM alert, or independently declare a user/device compromised.

## Playbook use

Security-capable playbooks should collect deterministic evidence first, then call the shared evaluator rather than embedding playbook-specific freeform threat prompts. The playbook/policy layer decides the next state/action from the validated assessment while preserving all ordinary approval and disruption controls.

`Jason - Windows HOSTS File Drift` v0.1.0 is the first draft playbook bound to `PROMPT-SEC-001`.

## Acceptance — 2026-09-19

Tests prove that the evaluator passes only supplied evidence to the structured reasoning client, rejects invented evidence citations, requires human review for higher-risk/inconclusive classifications, requires affirmative benign evidence for a benign result, and fails closed on empty/duplicate evidence.

## Production composition status — 2026-09-19

`build_runtime_application()` now composes `SecurityTriageEvaluator` with the same already-governed structured reasoning client used by Jason conversation reasoning (`hosted_conversation_client` when enabled, otherwise the configured Ollama structured client). This reuses existing credentials, transports, schema adapters, and model governance rather than introducing a new AI provider path. The evaluator is attached only as an internal runtime service and is not automatically invoked by arbitrary tickets until a playbook explicitly calls it.
