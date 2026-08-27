# Hosted Conversation Interpretation Acceptance Evidence

**Date:** 2026-08-20  
**Project:** Jason  
**Capability:** `conversation.intent.interpret`  
**Hosted provider:** OpenAI  
**Model:** `gpt-5.4-nano`  
**Execution mode:** Hosted AI, advisory interpretation only  
**Operational execution authority:** None  

## Purpose

Validate the governed hosted Conversation Kernel proposal path before production deployment.

The acceptance path tested:

1. Local deterministic hosted-egress classification.
2. OpenBao credential resolution.
3. Canonical provider, pricing, and execution-policy registration.
4. Governed GPT-5.4-nano proposal.
5. Jason structured proposal validation.
6. Independent local Ollama semantic review.
7. Deterministic Conversation Kernel outcome enforcement.
8. Durable usage accounting.
9. Prompt-free / target-free durable hosted audit.
10. Local denial of restricted hosted egress.

The hosted model was not granted connector, capability execution, provider selection,
or other operational authority.

## Production-Shaped Resource Contract

The Conversation Kernel was supplied the runtime-owned structural resource vocabulary:

- `endpoint`

The model was therefore not permitted to invent resource classes such as hardware
component names, provider-specific types, or implementation concepts.

This reflects the architectural rule that structural runtime vocabulary is Jason-owned
and reasoning models interpret the human's information need within that bounded vocabulary.

## Ordinary Hardware Acceptance

The following previously unmapped hardware questions were tested:

| Case | Result | Target Kind | Hosted Calls | Hosted Proposal |
| --- | --- | --- | ---: | --- |
| RAM | PASS | endpoint | 1 | First attempt accepted |
| CPU | PASS | endpoint | 1 | First attempt accepted |
| BIOS | PASS | endpoint | 1 | First attempt accepted |
| Free disk space | PASS | endpoint | 1 | First attempt accepted |
| Last logged-on user | PASS | endpoint | 1 | First attempt accepted |
| DIMM / memory-module speed | PASS | endpoint | 1 | First attempt accepted |
| GPU / graphics card | PASS | endpoint | 1 | First attempt accepted |
| Motherboard | PASS | endpoint | 1 | First attempt accepted |

**Acceptance:** `8/8 PASS`

No hardware-fact-specific routing rules, JSON pointer maps, motherboard rules,
DIMM rules, RAM rules, or equivalent semantic fact mappings were introduced to
achieve this result.

## Restricted Hosted-Egress Acceptance

The following classes were tested:

| Restricted request | OpenAI calls | Result |
| --- | ---: | --- |
| Administrator password | 0 | PASS |
| API key | 0 | PASS |
| Medical information | 0 | PASS |
| Payment-card information | 0 | PASS |

**Acceptance:** `4/4 PASS — zero hosted provider calls`

Restricted requests were blocked from hosted reasoning by the local deterministic
egress policy.

The payment-card case returned a local Conversation Kernel result after hosted egress
was blocked. The semantic content of that local result was not captured in this
acceptance run and remains a separate follow-up item. This does not alter the
zero-egress result.

## Hosted Usage

Production-shaped acceptance run:

- Hosted attempts: 8
- Input tokens: 5,509
- Output tokens: 862
- Total tokens: 6,371
- Total calculated hosted cost: `$0.00217930`
- Average calculated cost per hosted attempt: `$0.0002724125`

Calculated cost was derived from measured provider token usage rather than the
pre-execution estimate.

Pre-execution estimates remain separately attributable in the usage ledger.

## Latency

Ordinary reviewed interpretation:

- Mean: 11.052 seconds
- Median: 10.816 seconds
- Maximum: 12.138 seconds

Earlier isolated hosted-provider measurements were materially faster than the full
reviewed path. The remaining latency is therefore tracked separately as an
optimization workstream, with local semantic review currently contributing a
significant portion of interactive latency.

Latency optimization is not permitted to weaken the independent review,
deterministic validation, egress, authority, audit, or evidence controls.

## Privacy / Audit Acceptance

Durable hosted audit validation:

- Prompt body absent: PASS
- Endpoint identifier absent: PASS
- Restricted prompt body absent: PASS
- Hosted usage ledger persisted independently: PASS
- Usage database restrictive mode `0600`: previously proven PASS

## Accounting Acceptance

Prior no-build accounting proof established:

- Measured token cost calculation: PASS
- Post-execution calculated cost: PASS
- Pre-execution estimate retained separately: PASS
- Rejected provider response usage retained: PASS
- Rejected provider response calculated cost retained: PASS

This prevents failed/retried hosted attempts from disappearing from cost attribution.

## Clarification Policy Evidence

A prior isolated motherboard interpretation proposed an unnecessary clarification.

When executed through the actual Reviewed Conversation Kernel, the request resolved as
bounded endpoint information rather than requiring the human to repeat or classify
the target.

This demonstrates that model proposals remain advisory and Jason's review /
deterministic policy boundary controls the accepted interpretation.

## DIMM Diagnostic Evidence

The prior unconstrained benchmark failed the DIMM-speed request.

A production-shaped diagnostic with runtime resource kind `endpoint` produced:

- Correct endpoint target: PASS
- Correct memory-module-speed information need: PASS
- First hosted attempt accepted: PASS
- Local independent review completed: PASS
- Safe durable audit: PASS

The failure was therefore not a DIMM-specific reasoning limitation. It resulted from
the earlier benchmark allowing the model to invent structural resource kinds.

No DIMM-specific remediation was introduced.

## Acceptance Decision

### Hosted interpretation design

**PASS**

### Hosted egress controls

**PASS**

### Usage / cost accounting

**PASS**

### Production-shaped Conversation Kernel

**PASS**

### Production deployment verification

**PENDING**

These results authorize proceeding to a controlled production deployment and live
verification. They do not, by themselves, mark the production provider, capability,
credential binding, usage ledger, or hosted-egress components as production verified.

System Registry verification should occur only after deployed-state and live
end-to-end evidence are captured.

## Remaining Follow-Up

1. Controlled deployment and live Teams proof.
2. Confirm actual Datto evidence fulfillment for multiple generic hardware questions.
3. Verify payment-card local fallback semantic outcome.
4. Reduce interactive review latency without weakening governance.
5. Continue toward retirement of legacy semantic fact mappings after the generic
   fulfillment path is live-proven.
