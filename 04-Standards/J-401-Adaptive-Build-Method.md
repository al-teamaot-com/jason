# J-401 — Adaptive Build Method

**Version:** 0.1  
**Status:** Approved engineering standard  
**Owner:** Jason Architecture Authority

## Purpose

This standard defines how Jason is built while preserving architectural discipline and learning from real implementation.

Jason will not attempt to predict every future case before development begins. The framework must be stable enough to guide implementation and adaptable enough to improve when reality reveals a gap.

## 1. Core development loop

```text
Architecture
    ↓
Implement
    ↓
Observe
    ↓
Learn
    ↓
Adjust architecture or implementation
    ↓
Repeat
```

Architecture remains authoritative but alive.

## 2. Vertical slices before horizontal frameworks

Jason shall be developed through complete, useful capabilities that exercise the kernel end to end.

A preferred slice includes:

```text
Request
    ↓
Identity and authority
    ↓
Evidence collection
    ↓
Memory and correlation
    ↓
Reasoning
    ↓
Policy evaluation
    ↓
Recommendation or action
    ↓
Communication
    ↓
Verification
    ↓
Learning
```

The project should not build every generic subsystem in isolation before delivering a useful outcome.

## 3. Concrete before generic

Build a real capability before inventing a universal framework for that capability class.

Examples:

- Build Disk Health Investigation before a universal diagnostic framework.
- Build Mail Investigation before a universal cloud investigation framework.
- Build multiple working capabilities before extracting a shared abstraction.

A common framework should be extracted only after operating evidence demonstrates a stable common pattern.

## 4. Working capability over perfect framework

A working, governed capability is more valuable than a theoretically complete framework that has not produced an organizational outcome.

This does not permit unsafe shortcuts. Identity, authority, tenant isolation, evidence provenance, auditability, and failure safety are mandatory from the beginning.

## 5. Framework-change test

When implementation conflicts with the current design, the team must determine whether it discovered:

- an implementation defect;
- an incomplete specification;
- a missing architectural concept;
- a provider-specific constraint;
- an unjustified assumption;
- a genuinely new business requirement.

The team shall not silently patch around an architectural conflict.

A framework change should identify the concrete lesson or operating evidence that justified it.

## 6. Architecture stability levels

### Constitution

Changes slowly. Amend only when the enduring mission, principles, or governance truly require correction.

### Canonical models and professional principles

Change deliberately when multiple implementations or real operating cases reveal a durable improvement.

### Kernel specifications

May evolve during early builds, but changes must remain versioned, reviewed, and traceable.

### Capability specifications and provider implementations

Expected to evolve frequently during pilot and stabilization.

## 7. Minimum viable professional

The first Jason build need not know everything. It must consistently demonstrate these behaviors:

1. Listen and establish context.
2. Observe and preserve evidence.
3. Reason without fabricating.
4. Communicate proportionately.
5. Remember the outcome and lesson.
6. Identify an improvement opportunity where justified.

## 8. Capability graduation

Every capability progresses through governed maturity stages:

1. Observe.
2. Recommend.
3. Execute with approval.
4. Execute autonomously within bounded policy.
5. Optimize under governance.

Graduation requires evidence, not enthusiasm.

Required evidence may include:

- measured accuracy;
- successful outcome rate;
- appropriate escalation rate;
- absence of tenant-boundary violations;
- verified audit completeness;
- human acceptance;
- predictable failure behavior;
- demonstrated rollback or takeover paths.

## 9. Required sprint outcome

Every sprint should leave Jason demonstrably more useful, safer, easier to understand, or easier to maintain.

Infrastructure-only work is acceptable only when it is directly tied to an active vertical slice and has a clear acceptance test.

## 10. First build sequence

The approved first vertical slice is:

**CAP-001 — Professional Ticket Investigation**

Initial flow:

```text
Ticket received
    ↓
Requester and client context resolved
    ↓
Authority evaluated
    ↓
Ticket and diagnostic evidence preserved
    ↓
Observations separated from inference
    ↓
Hypotheses ranked
    ↓
Recommendation produced
    ↓
Technician-facing summary presented
    ↓
Outcome and learning candidate recorded
```

Version 0.1 is recommendation-only. It shall not perform operational remediation.

## 11. Initial engineering metric

The primary early metric is **Time to Useful Answer**: the time between receipt of a valid ticket investigation request and delivery of an evidence-grounded response that helps a technician take the next appropriate action.

Supporting metrics include:

- evidence citation completeness;
- technician acceptance rate;
- appropriate uncertainty;
- escalation quality;
- client-boundary violations;
- unverified completion claims;
- verified outcome capture.

## 12. Deliberate non-goals

The first build shall not attempt to provide:

- universal automation;
- broad autonomous execution;
- every vendor connector;
- distributed microservices merely for scale;
- a sophisticated self-modifying policy engine;
- a universal reasoning framework before working capabilities exist;
- exhaustive coverage of every MSP scenario.

## 13. Governing rule

Architecture shall not be changed merely because of opinion, convenience, or novelty. It should change when reality, evidence, risk, or a material platform improvement teaches the project something worth preserving.
