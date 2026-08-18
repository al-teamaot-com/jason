# Teams Conversation Working Baseline Reset

**Date:** 2026-08-18  
**Status:** Active engineering baseline  
**Workstream:** Teams conversational read path  
**Branch:** `feature/jason-runtime-service`

## Purpose

This document resets the Teams conversational read workstream around a simple rule:

> Establish and preserve a reliably working end-to-end baseline first, then add constitutional requirements one at a time without losing that baseline.

The baseline is not the final Jason architecture. It is a controlled reference implementation used to prove transport, identity, authority, orchestration, provider execution, evidence return, and user-visible response delivery independently from newer semantic and conversational experiments.

## Working-Baseline Method

For this workstream Jason will use the following development sequence:

1. Review the existing implementation and identify components already proven in live operation.
2. Assemble the smallest end-to-end path from those proven components.
3. Prove that path with multiple unrelated live reads.
4. Freeze the known-good behavior with automated regression coverage and live evidence.
5. Add one constitutional requirement or architectural improvement at a time.
6. Re-run the baseline proof after every step.
7. If a step breaks the baseline, revert or isolate that step before proceeding.
8. Record both successful and failed approaches so failed designs are not rediscovered later.

## Narrow Initial Success Definition

The initial baseline succeeds when:

> Jason receives a natural Teams question about an identifiable resource, resolves it to an existing governed read capability, executes that capability through the Central Orchestrator, obtains provider evidence, and returns a supported answer to Teams reliably.

The initial baseline does **not** need to prove all future conversational behaviors at once.

## Components Already Proven and Retained

The following components are retained because they have either passed repeated automated validation, live proof, or both:

- OpenClaw / Teams authenticated ingress.
- Trusted machine identity and replay protection.
- Microsoft identity to Jason principal binding.
- Jason organization / principal authority context.
- `GovernedTeamsOrchestrationRequestFactory`.
- Central Orchestrator authority enforcement.
- Capability Registry and Execution Provider Registry.
- Datto RMM connector and governed connector invoker.
- Provider execution deadline enforcement.
- Orchestration event audit trail.
- Teams return-path transport.
- Existing conversation continuation store.
- Existing provider-neutral endpoint read capability contracts.

These components are not being redesigned as part of the baseline reset unless later evidence demonstrates a defect in one of them.

## Existing Runtime Seam

The runtime already supports two conversation paths behind `JASON_DYNAMIC_CONVERSATION_ENABLED`.

When dynamic conversation is disabled, the runtime composes the existing `TeamsConversationFlow` and its legacy intent/evidence components while retaining the same identity binder, request factory, Central Orchestrator, providers, audit stores, continuation store, and return transport used by the dynamic path.

This makes the legacy flow the preferred first baseline candidate because it minimizes simultaneous variables.

## Known Constitutional Gap in the Baseline Candidate

The legacy resolver currently depends on semantic mapping / canonical fact infrastructure and therefore does **not** represent the final constitutional architecture.

That is acceptable only for the controlled baseline phase.

The baseline must be clearly marked as transitional and must not be mistaken for the final design. Static semantic mappings remain prohibited as the destination architecture.

The purpose of temporarily using this path is to answer a narrower engineering question:

> Can the already-proven Teams, identity, authority, orchestration, provider, evidence, and return-path components form a reliable end-to-end conversational read when the newer dynamic semantic layers are removed from the critical path?

## What Has Worked

### Teams and identity boundary

Authenticated Teams requests have repeatedly reached Jason with the expected conversation, request, and correlation identifiers.

### Central Orchestrator path

Governed read requests have successfully crossed the Central Orchestrator with policy resolution, provider selection, invocation, completion, and audit events.

### Datto provider execution

After bounded provider execution was implemented, the Datto endpoint search capability completed in roughly seconds rather than the earlier approximately 90-second failure mode.

### Provider evidence acquisition

`endpoint.device.search` has repeatedly returned governed Datto evidence successfully during live tests.

### Planner output budget correction

The dynamic planner originally failed because its structured response exceeded its generation budget. Increasing the dedicated planning budget allowed planning to complete and orchestration to begin.

This proves the earlier pre-orchestration JSON failure was a model-output-contract problem rather than a Teams, identity, orchestration, or Datto problem.

## What Has Not Worked Reliably

### Fully dynamic multi-stage conversational path

The current dynamic path remains too dependent on serial local-model passes for simple factual reads.

Observed stages have included planning, argument binding, evidence selection, additional capability fulfillment, and previously response observation. The combined latency has repeatedly exceeded a reasonable Teams turn lifetime.

### Over-broad capability planning

A simple endpoint factual question caused the dynamic planner to select both `endpoint.device.search` and `endpoint.alert.history.search` even though the second capability was not evidently required by the human request.

### Model-based evidence sufficiency on the critical path

After a successful `endpoint.device.search`, the evidence reasoning stage consumed a large prompt and approximately tens of seconds. When it did not classify the evidence as sufficient, the flow continued to another capability and another large evidence-model call.

### Progressive fulfillment attempt

Progressive fulfillment correctly introduced a mechanism to stop after sufficient evidence, but the live path still classified the first endpoint result as insufficient and therefore proceeded to the second capability. The second evidence-model call again timed out.

The mechanism itself may remain useful later, but it did not solve the current reliability problem because evidence sufficiency still depended on a slow semantic model decision.

### Repeated budget increases as a solution

Increasing output token ceilings fixed one specific structured-output failure class, but token-budget changes do not address the larger problem of too many serial reasoning passes in the critical path.

Further budget tuning should not be treated as the primary architecture strategy.

## Lessons From Failed Iterations

1. A fast provider cannot compensate for a model-heavy synchronous conversation pipeline.
2. Passing unit tests does not prove Teams turn viability; live latency and transport lifetime are first-class acceptance criteria.
3. Dynamic discovery, dynamic binding, dynamic evidence interpretation, and multi-resource fulfillment should not all be introduced simultaneously.
4. The Central Orchestrator, identity boundary, and Datto execution path are not the current bottleneck and should remain stable while the conversation layer is simplified.
5. A working baseline must exist after every architectural step so a regression can be attributed to one change.
6. The original triggering question is a regression fixture, not the specification.

## Failed-Approach Record Format

Every materially failed approach in this workstream will be recorded using:

- **Hypothesis** — what we expected to improve.
- **Change** — what was introduced.
- **Observed result** — what happened in automated and live testing.
- **Failure class** — the abstraction-level reason it failed.
- **Lesson** — what the architecture should preserve or avoid.
- **Do not repeat** — the specific anti-pattern that should not be reintroduced without new evidence.

## Baseline Validation Plan

The first baseline validation should intentionally be small.

### Phase 1 — Single resource, single fact

Use the existing non-dynamic conversation path and prove multiple unrelated reads against an identifiable endpoint or other governed resource.

Success requires:

- one Teams turn,
- one resolved governed capability where one is sufficient,
- normal Central Orchestrator execution,
- successful provider evidence,
- one natural Teams response,
- no transport expiration,
- no direct provider or agent bypass.

### Phase 2 — Baseline freeze

Once Phase 1 passes repeatedly:

- record exact runtime configuration,
- record live evidence and timing,
- add regression tests around the observed contract,
- mark the baseline commit as the known-good reference for this workstream.

### Phase 3 — Constitutional evolution

Add requirements individually in the following general order, re-proving the baseline after each change:

1. Remove static question / fact mappings from interpretation.
2. Replace static mapping with runtime capability discovery while retaining single-capability execution.
3. Ground selector binding dynamically.
4. Add provider-independent conversation continuity.
5. Add dynamic evidence interpretation only where deterministic evidence contracts cannot answer safely.
6. Add bounded multi-capability fulfillment for genuinely multi-part information needs.
7. Add cost / model escalation and richer conversational synthesis.

The exact order may change if evidence shows a lower-risk sequence, but only one major behavior should be introduced at a time.

## Guardrail During Baseline Phase

The following rule applies until the workstream exits baseline phase:

> Do not add a new semantic layer, fallback, model pass, or multi-resource behavior merely to make one failed live question pass. First prove the current baseline, then introduce one general capability with an independent acceptance test.

## Exit Criteria

This reset is complete when Jason has a documented, repeatable known-good Teams conversational read baseline and every later constitutional improvement can be compared against that baseline for correctness, latency, evidence quality, governance, and operational reliability.
