# Jason AI Prompt Registry

## Section Goal

Give the AOT Owner a single secret-safe Grafana view of the material AI prompts that influence Jason's production reasoning, where each prompt is used, its version/source fingerprint, and whether the registered definition still matches source. Prompt content remains governed source and is not copied into Prometheus.

## Canonical model

A material AI prompt is represented as a versioned `PromptDefinition` identified by a stable `prompt_id`. The source registry is `implementation/orchestrator/prompt_registry.json`.

The registry intentionally covers prompts that materially affect AI interpretation, planning, reasoning, routing, or response generation. Test-only prompts, provider payload data, user input, dynamically assembled evidence, and trivial implementation strings are not separate registry entries unless they become durable behavior contracts.

Each registry entry records:

- stable prompt ID and friendly name;
- semantic version and lifecycle;
- runtime surface / purpose;
- model profile;
- risk classification;
- structured-output and tool-access flags;
- source path and source symbol;
- SHA-256 fingerprint of the complete prompt text;
- owner; and
- runtime invocation telemetry status.

The full prompt text is never exported as a Prometheus label or Grafana field.

## Source-integrity rule

`infrastructure/showcase/prompt_exporter.py` reads the registry and re-extracts each registered static prompt from its exact source symbol. It calculates the source SHA-256 and compares it with the registered fingerprint.

`jason_ai_prompt_source_hash_match{prompt_id=...}` is `1` only when the source still exactly matches the registered prompt content. A source change without a corresponding version/registry update therefore becomes observable drift instead of silently changing production AI behavior.

## Grafana

Dashboard UID: `jason-ai-prompt-registry`

The initial dashboard shows:

- number of registered material prompts;
- source drift count;
- source-hash coverage percentage;
- invocation-telemetry readiness;
- complete prompt metadata inventory;
- per-prompt source-integrity status; and
- prompt counts by runtime surface.

Grafana is observational only. It grants no authority to edit prompts, change models, approve actions, or alter Jason governance.

## Runtime invocation telemetry

Initial implementation deliberately reports `jason_ai_prompt_invocation_telemetry_available 0` because the current runtimes do not yet emit a common per-prompt invocation event. Do not infer call volume, latency, token use, cost, or success rate until those events are actually instrumented.

The next phase should introduce a provider-neutral `PromptInvocation` record at the common model-call boundary with low-cardinality telemetry such as prompt ID/version, model profile, result class, latency, input/output token counts when supplied by the model provider, and tool-use flag. User text, full prompt text, evidence payloads, ticket IDs, device IDs, secrets, and other high-cardinality/sensitive values must not be Prometheus labels.

## Initial acceptance — 2026-09-19

The initial source registry contained 20 material prompts spanning conversation interpretation/planning, semantic query planning, investigation routing/reasoning/answer generation, evidence reasoning, response quality, semantic mapping, and endpoint-operations reasoning. On 2026-09-19, `PROMPT-SEC-001` (Security Threat/Benign Triage) was added, bringing the reviewed registry to 21 prompts. Exporter tests verify all registered prompt hashes against current source and verify that full prompt content is not exported in metrics.
