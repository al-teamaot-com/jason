# J-116 — State Model

**Status:** Approved Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Every governed object, workflow, decision, connector, service, and implementation represented by Jason

## 1. Purpose

The State Model defines how Jason describes the current condition and lifecycle of the objects in its world.

Jason must be able to answer:

1. What stage of its lifecycle is this object in?
2. Is it currently usable, healthy, verified, blocked, or in need of attention?
3. What caused the state to change?
4. Was the transition authorized and supported by evidence?
5. What must happen next?

The State Model provides a stable business vocabulary without requiring Jason to copy the status fields of Autotask, Datto RMM, IT Glue, Microsoft, OpenClaw, or any other provider.

## 2. Scope

This model defines:

- the difference between lifecycle state and current condition;
- common lifecycle states shared across governed objects;
- health, verification, attention, and execution dimensions;
- requirements for state transitions;
- rules for mapping provider-specific statuses;
- minimum state profiles for the canonical objects defined by J-117.

This model does not define:

- every provider status value;
- workflow implementation details;
- event transport or event schemas;
- detailed relationship semantics;
- user-interface labels or colors;
- product-specific automation behavior.

Those concerns belong to the Event, Relationship, Connector, Service, Workflow, and implementation models.

## 3. Foundational Principles

### 3.1 State describes reality, not a screen field

Jason records the business condition of an object. A provider status may be evidence of that condition, but it does not define Jason's canonical state.

### 3.2 Lifecycle and health are different

An Asset may be active but unhealthy. A Work Item may be open but blocked. A Connector may be enabled but degraded. Jason must not collapse these different meanings into one status value.

### 3.3 State must be attributable

Every material state transition must identify when it occurred, what caused it, who or what asserted it, and what evidence supports it.

### 3.4 Uncertainty remains visible

Jason must distinguish observed, verified, inferred, disputed, and unknown state. Lack of information is not proof of health, completion, or compliance.

### 3.5 Transitions are governed

A technically possible transition is not automatically authorized. Policy, authority, safety, evidence, tenant context, and approval requirements still apply.

### 3.6 Completion requires verification

Execution alone does not establish success. A Change, Task, Work Item, remediation, or automation should not be considered successfully completed until its required outcome is verified.

### 3.7 Preserve history

Jason records state history rather than overwriting the past. Material transitions must remain auditable.

### 3.8 Prefer the smallest useful vocabulary

Jason uses a limited set of canonical state dimensions and object-specific profiles. New states should be added only when they change governance, action, reporting, or meaning.

## 4. State Dimensions

A governed object may have several state dimensions at the same time. These dimensions must remain distinct.

### 4.1 Lifecycle State

Describes where the object is in its existence or business lifecycle.

Canonical lifecycle states are:

- **Candidate** — discovered, proposed, or inferred but not yet accepted as authoritative;
- **Planned** — approved or intended but not yet active;
- **Active** — currently in force, use, service, or operation;
- **Suspended** — temporarily inactive while remaining valid and recoverable;
- **Completed** — intended work or purpose has been fulfilled and verified;
- **Superseded** — replaced by another object or revision;
- **Retired** — intentionally removed from active use;
- **Cancelled** — intentionally ended before completion or activation;
- **Rejected** — evaluated and not accepted;
- **Expired** — no longer valid because its authorized time or term ended;
- **Unknown** — the lifecycle state cannot currently be established.

Not every object uses every lifecycle state.

### 4.2 Operational Condition

Describes whether the object can presently perform its expected function.

Canonical operational conditions are:

- **Normal** — functioning as expected;
- **Degraded** — functioning with reduced quality, capacity, reliability, or control;
- **Unavailable** — unable to perform its expected function;
- **Blocked** — unable to proceed because of a dependency, authority, policy, evidence, or external condition;
- **At Risk** — functioning now, but evidence indicates a material likelihood of failure or loss;
- **Not Applicable** — operational condition does not meaningfully apply;
- **Unknown** — insufficient evidence exists to determine the condition.

### 4.3 Health State

Describes the assessed health of an Asset, Service, Connector, environment, or other operational object.

Canonical health states are:

- **Healthy**;
- **Warning**;
- **Unhealthy**;
- **Critical**;
- **Unknown**;
- **Not Monitored**.

Health thresholds must be defined by policy, service expectation, baseline, or object-specific rules. A provider's red, yellow, or green indicator may be mapped to these values but is not automatically authoritative.

### 4.4 Verification State

Describes how confidently Jason knows the object's asserted condition or facts.

Canonical verification states are:

- **Unverified** — asserted or discovered but not yet validated;
- **Partially Verified** — some material elements are confirmed;
- **Verified** — sufficient authoritative evidence supports the assertion;
- **Disputed** — credible evidence conflicts;
- **Stale** — previously verified information may no longer represent current reality;
- **Unknown** — the verification posture cannot be determined.

### 4.5 Attention State

Describes whether human or governed system attention is required.

Canonical attention states are:

- **No Action Required**;
- **Monitor**;
- **Review Required**;
- **Action Required**;
- **Approval Required**;
- **Escalation Required**;
- **Emergency Action Required**.

Attention State does not itself grant authority to act.

### 4.6 Execution State

Used for work, tasks, projects, changes, investigations, and other executable objects.

Canonical execution states are:

- **Not Started**;
- **Queued**;
- **In Progress**;
- **Waiting**;
- **Blocked**;
- **Pending Approval**;
- **Pending Verification**;
- **Succeeded**;
- **Partially Succeeded**;
- **Failed**;
- **Cancelled**.

A successful command or provider job does not necessarily equal a successful business outcome. The required outcome must be verified.

## 5. State Record

Every material state assertion or transition must support the following information:

- canonical object identifier;
- state dimension;
- previous state where applicable;
- new state;
- effective time;
- observed or recorded time;
- source;
- actor or asserting authority;
- reason or triggering condition;
- supporting evidence;
- verification state;
- confidence where inference is involved;
- tenant and organizational context;
- applicable policy or approval;
- expected next review, expiration, or transition where known;
- audit reference.

## 6. State Transition Rules

A material transition is valid only when Jason can establish:

1. the object and tenant context;
2. the current known state;
3. the proposed new state;
4. the event or reason causing the transition;
5. the authority to assert or approve the transition;
6. applicable policy and safety constraints;
7. required supporting evidence;
8. whether verification is required after the transition;
9. the resulting next action, review, or escalation.

If these requirements cannot be satisfied, Jason must preserve the existing verified state and record the new information as unverified, disputed, or pending review.

## 7. Transition Controls

### 7.1 Allowed transitions

Each object profile may define permitted transitions. Implementations must not invent transitions solely because a provider permits a status change.

### 7.2 Guard conditions

A transition may require one or more guard conditions, including:

- verified authority;
- approval;
- maintenance window;
- evidence threshold;
- dependency completion;
- risk acceptance;
- tenant confirmation;
- communication to affected parties;
- rollback readiness;
- outcome verification.

### 7.3 Automatic transitions

Jason may perform an automatic transition only when policy explicitly allows it and the required confidence, safety, authority, and evidence thresholds are met.

### 7.4 Human-confirmed transitions

A human assertion may establish a state when the person has appropriate authority and the assertion is captured with sufficient context. Material or high-risk assertions may still require independent evidence.

### 7.5 Reversal and correction

When a state was recorded incorrectly, Jason does not erase the original record. It records a correction, the reason, the correcting authority, and the revised state.

## 8. Canonical Object State Profiles

The following profiles define the minimum useful lifecycle for J-117 objects. Implementations may add governed sub-states without replacing the canonical meaning.

### 8.1 Organization, Person, and Identity

Typical lifecycle:

**Candidate → Active → Suspended → Retired**

Additional valid outcomes include Rejected, Expired, or Superseded.

An inactive Person and a disabled Identity are different facts. Disabling an account must not imply that the Person no longer belongs to the organization.

### 8.2 Asset

Typical lifecycle:

**Candidate → Planned → Active → Suspended → Retired**

An Asset also carries Operational Condition and Health State. Active does not mean healthy, secure, supported, compliant, or online.

### 8.3 Service

Typical lifecycle:

**Planned → Active → Suspended → Retired**

A Service may be Active while Degraded or Unavailable. Service restoration changes Operational Condition; it does not necessarily change lifecycle state.

### 8.4 Agreement

Typical lifecycle:

**Candidate → Planned → Active → Expired or Terminated/Cancelled → Retired**

An Agreement may be Active while renewal, breach, review, or risk attention is required.

### 8.5 Request

Typical lifecycle:

**Received → Evaluating → Accepted or Rejected → Fulfilled → Closed**

For canonical mapping, Received and Evaluating are Active lifecycle sub-states; Fulfilled is Completed; Closed indicates administrative finalization.

A Request may create one or more Work Items but remains distinct from them.

### 8.6 Work Item and Task

Typical execution lifecycle:

**Not Started → Queued → In Progress → Pending Verification → Succeeded → Completed**

Alternative paths include Waiting, Blocked, Pending Approval, Partially Succeeded, Failed, or Cancelled.

Closure must not conceal unresolved risk, required follow-up, failed verification, or client communication obligations.

### 8.7 Alert

Typical lifecycle:

**New → Validating → Actionable, Suppressed, or Dismissed → Resolved → Closed**

An Alert is not automatically an Incident. Validation determines whether it represents a real condition, duplicate, expected behavior, false positive, or evidence requiring escalation.

### 8.8 Incident

Typical lifecycle:

**Declared → Investigating → Containing → Remediating → Recovering → Verifying → Resolved → Closed**

The exact response stages depend on incident type. Resolution requires evidence that the immediate adverse condition has ended or is controlled. Closure may additionally require communication, documentation, lessons learned, or corrective work.

### 8.9 Change

Typical lifecycle:

**Proposed → Assessing → Pending Approval → Approved → Scheduled → Implementing → Verifying → Completed**

Alternative outcomes include Rejected, Cancelled, Failed, Rolled Back, or Partially Completed.

A Change is not successful merely because the planned commands executed. The intended business and technical outcome must be verified.

### 8.10 Project

Typical lifecycle:

**Proposed → Planned → Approved → Active → Completing → Completed → Closed**

Alternative outcomes include On Hold, Blocked, Cancelled, or Failed.

### 8.11 Knowledge and Policy

Typical lifecycle:

**Draft → Review → Approved → Active → Superseded or Retired**

Knowledge may also be Stale or Disputed. Policy may also be Expired or Suspended. Draft material must not be silently treated as authoritative.

### 8.12 Evidence

Typical lifecycle:

**Collected → Validating → Verified → Retained → Disposed**

Alternative conditions include Rejected, Disputed, Corrupted, Superseded, or Legal Hold.

Disposal must comply with retention, legal, contractual, security, and policy requirements.

### 8.13 Decision and Approval

Typical lifecycle:

**Proposed or Requested → Evaluating → Issued → Active → Fulfilled, Expired, Revoked, or Superseded**

An Approval must retain its scope, conditions, authority, effective period, and permitted action. Approval for one action must not be generalized to another.

### 8.14 Capability

Typical lifecycle:

**Proposed → Evaluating → Approved → Available → Deprecated → Retired**

Capability availability is separate from provider health. A capability may remain Available through a substitute provider when one implementation fails.

### 8.15 Connector

Typical lifecycle:

**Proposed → Configuring → Testing → Enabled → Suspended or Disabled → Retired**

A Connector also carries Operational Condition, Health State, Verification State, and Attention State. Enabled does not mean healthy, authorized for every action, or correctly mapped.

## 9. Provider State Mapping

Every connector that imports or changes state must maintain an explicit mapping between provider statuses and Jason states.

A mapping must record:

- provider and resource type;
- provider status value;
- canonical state dimension and value;
- conditions or exceptions;
- mapping confidence;
- last validation date;
- responsible owner;
- treatment of unknown provider values.

Unknown or newly introduced provider statuses must fail visibly. They must not be silently mapped to Normal, Active, Completed, or Healthy.

## 10. Derived State

Jason may derive state from multiple facts or signals when no single authoritative source exists.

Derived state must include:

- the facts considered;
- the rule or reasoning used;
- confidence;
- last evaluation time;
- contradictory evidence;
- the conditions that would trigger reevaluation.

Derived state must remain distinguishable from directly observed or authoritative state.

## 11. State and Bounded Curiosity

When an object is Unhealthy, Degraded, Blocked, Failed, Unknown, or requires attention, Jason should not stop at labeling the condition.

Subject to authority and policy, Jason should determine:

1. what evidence would explain the state;
2. what the smallest useful next investigation is;
3. whether the condition can be safely resolved;
4. whether more evidence is justified;
5. when to stop, escalate, request approval, or communicate.

Evidence collection must be proportional. For example, Jason should obtain the relevant time range or filtered portion of a large log before retrieving the entire file unless broader collection is justified.

## 12. Constraints

1. No single status field may represent lifecycle, health, verification, attention, and execution at the same time.
2. No provider status may become canonical without an explicit mapping.
3. No unknown state may be silently treated as Normal, Healthy, Active, Verified, or Complete.
4. No completion state may be asserted when required outcome verification has failed or not occurred.
5. No automatic transition may exceed delegated authority or policy.
6. No state correction may erase the original audit history.
7. No object may transition across tenant or organizational boundaries through status mapping alone.
8. No disabled Identity may be treated as proof that the related Person is terminated.
9. No closed Work Item may be treated as proof that the underlying Request, Incident, risk, or obligation is resolved.
10. No health assessment may be treated as permanent; it must retain its observation time and evidence context.

## 13. Conformance Requirements

An implementation conforms to J-116 when it:

1. separates lifecycle state from operational condition, health, verification, attention, and execution;
2. preserves material transition history;
3. records source, actor, reason, evidence, and time for material state changes;
4. maps provider statuses explicitly;
5. preserves uncertainty and conflicting evidence;
6. verifies required outcomes before asserting successful completion;
7. applies policy and authority before automatic transitions;
8. supports object-specific state profiles without redefining canonical meanings;
9. treats unknown provider states safely and visibly;
10. supports bounded investigation and appropriate next-action determination for adverse states.

## 14. Architect's Rationale

The MSP business is full of misleading status labels. A ticket may be closed while the user's problem remains. A device may be active while critically unhealthy. A Microsoft account may be disabled while the employee remains active. A Datto job may report success while the intended remediation did not occur.

Jason therefore requires a state model that represents business reality rather than copying vendor fields. Separating lifecycle, condition, health, verification, attention, and execution prevents false conclusions while keeping the model understandable.

The model intentionally uses a small canonical vocabulary. It provides enough structure for safe orchestration, troubleshooting, reporting, communication, and audit without turning Jason into a replacement PSA, RMM, workflow engine, or monitoring platform.

This model should be revised when operational evidence shows that an important business condition cannot be represented without ambiguity, or when a state distinction materially changes governance, action, reporting, or risk.