# Jason Failure-Class Resolution Standard

## Rule

Jason engineering must not implement single-example fixes.

A test case, user sentence, provider response, device identifier, ticket, error string, or integration failure may expose a problem, but it must not define the production correction.

## Required correction record

Before corrective implementation, record:

- **Observed symptom:** the concrete event that exposed the weakness.
- **Failure class:** the broader procedural or architectural category that can produce equivalent failures.
- **Violated invariant:** the Jason rule that should have prevented the class of failure.
- **General correction:** the abstraction-level change that fixes the class without encoding the triggering example.
- **Regression diversity:** at least one unrelated case exercising the same invariant, and additional cross-domain cases when the change affects shared orchestration or conversation behavior.

## Prohibited corrective patterns

Unless independently justified as a governed domain rule, corrective work must not introduce:

- question-to-field mappings;
- phrase-to-provider routing;
- provider selection based on a triggering sentence;
- one-off scripts for a single information request;
- device/client/ticket-specific production branches;
- canned response patches that mask an unresolved backend failure class;
- model-specific prompt rules whose only purpose is to make one regression sentence pass;
- first-match resource/provider selection when ambiguity exists.

## Preferred corrective patterns

Prefer:

- stronger contracts and validation;
- structural resource metadata;
- provider-independent information needs;
- runtime capability/resource discovery;
- progressive evidence acquisition;
- verified conversation context;
- model retry/escalation behind one interface;
- generalized evidence and response-quality gates;
- explicit fail-closed ambiguity handling;
- audit evidence that makes the failure class observable.

## Review question

Every corrective change should be reviewable with one question:

> If the original triggering example had never existed, would this change still be a sensible architectural improvement for Jason?

If the answer is no, the proposed change is probably too narrow.
