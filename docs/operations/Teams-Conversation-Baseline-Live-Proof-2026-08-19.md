# Teams Conversation Baseline Live Proof

**Date:** 2026-08-19  
**Status:** Live baseline evidence  
**Workstream:** Teams conversational read path  
**Runtime mode:** `JASON_DYNAMIC_CONVERSATION_ENABLED=false`

## Purpose

Record the first live results from the controlled non-dynamic Teams conversation baseline after the runtime was successfully recreated from the already-installed `jason-runtime:local` image without rebuilding it.

This record distinguishes three separate outcomes: successful governed fulfillment, recognized-but-unauthorized fact requests, and transport/observability delay. These outcomes must not be collapsed into a single generic conversation failure.

## Runtime baseline

The baseline deployment completed with:

```text
BASELINE_MODE=PASS
JASON_DYNAMIC_CONVERSATION_ENABLED=false
READY_FOR_LIVE_TEST=1
```

The baseline therefore exercised the existing non-dynamic conversation path while retaining the current Teams/OpenClaw ingress, identity binding, Central Orchestrator, capability/provider registries, Datto RMM connector, evidence path, audit stores, and return transport.

## Live questions and outcomes

### 1. Logged-in user

Human request:

```text
Who is logged into AOT-50107?
```

Observed Jason response:

```text
AOT-50107 — last logged in user: AzureAD\ArnoldHeath. Source: datto_rmm.
```

**Classification:** successful governed fulfillment.

This proves the baseline can receive a natural Teams question about an explicitly identified endpoint, resolve it to an existing governed read path, obtain authoritative Datto evidence, and return a concise supported answer.

The response arrived after an apparent delay. A capture taken before delivery showed no matching security, orchestration, Ollama, gateway-completion, or gateway-failure event. That timing/observability anomaly remains a separate interface/telemetry issue and must not be treated as a semantic or provider failure without further evidence.

### 2. IP address

Human request:

```text
What is the IP address of AOT-50107?
```

Observed Jason response:

```text
I recognized that as a request for ip address, but Jason does not currently have a governed read capability that declares authority to retrieve that fact. No provider request was made.
```

**Classification:** recognized information need, governed capability/authority coverage gap.

The conversation layer understood the requested fact and target. Jason intentionally did not invoke a provider because no currently declared governed read capability asserted authority for that fact.

This is not evidence that Teams, identity, orchestration, Datto connectivity, or semantic interpretation failed.

### 3. Endpoint last seen

Human request:

```text
When was AOT-50107 last seen?
```

Observed Jason response:

```text
I recognized that as a request for endpoint last seen, but Jason does not currently have a governed read capability that declares authority to retrieve that fact. No provider request was made.
```

**Classification:** recognized information need, governed capability/authority coverage gap.

As with the IP-address request, the information need was understood but no provider invocation was authorized because the current capability metadata does not declare authority to retrieve that fact.

## What this baseline proves

1. The non-dynamic Teams conversation path is operational for at least one real endpoint fact.
2. Natural-language recognition can succeed independently from provider invocation authority.
3. Governed refusal behavior works: Jason can decline to query a provider when no declared capability authorizes the requested fact.
4. The current limitation for IP address and endpoint last-seen is capability/evidence authority coverage, not a reason to add phrase-specific routing or static question mappings.
5. The logged-in-user result is a valid known-good reference point for later architectural changes.

## What this baseline does not prove

- It does not prove arbitrary endpoint facts are currently covered.
- It does not prove multi-fact or multi-resource fulfillment.
- It does not prove the current static semantic/canonical-fact infrastructure is constitutionally acceptable as the destination architecture.
- It does not explain the observed response-delivery/telemetry delay.
- It does not justify adding hard-coded mappings for IP address, last-seen time, AOT-50107, or Datto-specific provider fields.

## Next architectural step

Do not patch the two rejected questions individually.

The next work should identify the abstraction-level gap between an existing governed endpoint resource capability and the facts that resource can authoritatively expose. The target is a reusable, capability/resource-driven contract that can declare discoverable supported observations and evidence without hard-coding human phrases or provider-specific question mappings.

The working invariant is:

> If an authorized provider-backed resource already returns a fact as part of its governed evidence contract, Jason should be able to discover that fact's availability and authority through reusable capability metadata rather than a question-specific mapping.

Any implementation must preserve identity-first authorization, Central Orchestrator authority, provider independence above the connector boundary, evidence provenance, and the prohibition on static question-to-field mappings.
