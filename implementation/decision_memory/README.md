# Decision Memory

Decision Memory lets Jason reuse previously verified conclusions before invoking new model reasoning.

## Constitutional fit

This subsystem is constitutional because it does not grant new authority. It reuses evidence-backed knowledge under the same policy, approval, scope, verification, audit, and escalation controls that govern the original action.

A cached result is never treated as universally true. It is valid only when:

- required evidence is present;
- applicability conditions match;
- exclusion conditions are absent;
- the record has not expired or been invalidated;
- client and organization scope match policy;
- the proposed action is still permitted;
- verification remains mandatory after execution.

Decision Memory may reduce model calls, but it may not bypass authorization, safety controls, or human approval requirements.

## Processing order

1. Normalize ticket and environment facts.
2. Evaluate deterministic rules.
3. Search exact verified decision memory.
4. Search verified pattern memory.
5. Retrieve similar historical cases as evidence.
6. Invoke an approved model only when needed.
7. Route any action through the governed remediation orchestrator.
8. Verify the outcome and update memory statistics.

## Memory classes

- `exact`: an exact normalized fingerprint match.
- `pattern`: a bounded reusable rule covering allowed variations.
- `similar_case`: historical evidence only; never direct authority to act.

## Non-negotiable controls

- No raw ticket-text-to-answer cache.
- No cross-client reuse of client-sensitive facts.
- No automatic widening of applicability.
- No execution authority stored in memory.
- No silent use of expired or degraded records.
- Every reuse decision is auditable.
- Failures reduce trust and can automatically suspend a record.
- Promotion from similar case to pattern requires approval.

## Initial pilot

Begin with low-risk workstation patch tickets. Servers, domain controllers, security incidents, compliance-impacting actions, registry changes, firewall changes, identity changes, and Microsoft 365 permission changes remain excluded unless separately approved.