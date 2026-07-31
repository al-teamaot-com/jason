# Jason Capability Catalog

Status: Initial approved catalog
Version: 0.1

## 1. Purpose

The Jason Capability Catalog is the authoritative inventory of functions exposed by the Jason platform.

Consumers request named capabilities rather than invoking agents, services, vendor APIs, or implementation-specific endpoints directly. The orchestrator resolves the request to an approved implementation, applies identity and policy controls, transfers only required context, records evidence, handles retries and timeouts, and assembles the final result.

## 2. Naming standard

Capability names use lowercase dot-separated identifiers:

```text
<domain>.<resource>.<action>
```

Examples:

```text
identity.workload.authenticate
secrets.secret.read
governance.action.evaluate
autotask.ticket.create
```

Names describe business or platform intent, not vendor implementation details.

## 3. Required capability record

Every capability entry shall define:

- capability name;
- current version;
- lifecycle state;
- owner service;
- business purpose;
- input schema;
- output schema;
- invoking identities and roles;
- governance requirements;
- approval requirements;
- evidence requirements;
- dependencies;
- idempotency behavior;
- timeout and retry policy;
- data classification;
- tenant or client isolation rules;
- failure behavior;
- review interval;
- deprecation and retirement criteria.

## 4. Invocation rules

- Agents may request named capabilities only through the central orchestrator.
- Agents shall never invoke or communicate with other agents directly.
- A capability request does not grant permission to execute it.
- Identity verification and governance evaluation occur before governed execution.
- Secret values shall never be included in capability requests or results.
- Large artifacts and evidence shall be passed by centrally managed references.
- Capability results shall be structured and versioned.
- Provider-specific behavior belongs in adapters, not the capability contract.
- State-changing capabilities shall support idempotency where technically possible.

## 5. Standard result envelope

Capabilities should return a common result envelope:

```json
{
  "capability": "example.resource.action",
  "version": "1.0",
  "request_id": "uuid",
  "correlation_id": "uuid",
  "status": "succeeded|failed|denied|pending_approval|deferred",
  "result": {},
  "evidence_reference": "evidence://...",
  "errors": []
}
```

Results must not expose provider credentials, authorization headers, unseal materials, private keys, or plaintext secrets.

## 6. Initial platform capabilities

### 6.1 Identity

#### `identity.workload.authenticate`

- Owner: Jason Identity Service
- Purpose: Authenticate a service, workload, or approved automation identity.
- State: planned
- Governance: platform identity policy
- Evidence: identity, authentication method, outcome, timestamp
- Failure behavior: fail closed

#### `identity.human.authenticate`

- Owner: Jason Identity Service
- Purpose: Authenticate a human operator through an approved identity provider.
- State: planned
- Governance: human access and MFA policy
- Evidence: operator identity, method, outcome, timestamp
- Failure behavior: fail closed

#### `identity.authorization.resolve`

- Owner: Jason Identity Service
- Purpose: Resolve identity attributes, roles, scopes, and tenant boundaries for governance evaluation.
- State: planned
- Governance: identity and role policy
- Evidence: identity, resolved roles and scopes, outcome
- Failure behavior: fail closed

#### `identity.credential.issue`

- Owner: Jason Identity Service
- Purpose: Issue a short-lived workload credential or certificate after authorization.
- State: planned
- Governance: privileged; approval may be required based on scope
- Evidence: recipient identity, credential class, validity period, outcome; never the credential value
- Failure behavior: fail closed

#### `identity.credential.revoke`

- Owner: Jason Identity Service
- Purpose: Revoke a workload credential, certificate, or trust relationship.
- State: planned
- Governance: privileged action
- Evidence: requesting identity, target identity, reason, outcome
- Failure behavior: retry safely and escalate on failure

### 6.2 Secrets

#### `secrets.secret.read`

- Owner: Jason Secrets Broker
- Purpose: Resolve a provider-neutral secret reference for an authorized workload.
- State: planned
- Initial provider: OpenBao adapter
- Governance: least privilege, purpose-bound access
- Evidence: requesting identity, secret reference, purpose, outcome; never the secret value
- Failure behavior: fail closed

#### `secrets.secret.write`

- Owner: Jason Secrets Broker
- Purpose: Create or update an approved secret through the configured provider.
- State: planned
- Governance: privileged; human approval normally required
- Evidence: requesting identity, reference, metadata change, approval, outcome
- Failure behavior: fail closed and avoid partial updates

#### `secrets.secret.rotate`

- Owner: Jason Secrets Broker
- Purpose: Rotate a secret or invoke a provider-specific rotation adapter.
- State: planned
- Governance: privileged and policy-controlled
- Evidence: reference, requester, approval, old/new version metadata, verification outcome
- Failure behavior: retain or restore last known valid credential when supported

#### `secrets.credential.revoke`

- Owner: Jason Secrets Broker
- Purpose: Revoke a leased or dynamically issued external credential.
- State: planned
- Governance: authorized workload or emergency revocation policy
- Evidence: credential metadata, reason, requester, outcome
- Failure behavior: retry and escalate

#### `secrets.provider.health`

- Owner: Jason Secrets Broker
- Purpose: Report provider connectivity, seal state, adapter state, and readiness without exposing sensitive details.
- State: planned
- Governance: operational read
- Evidence: optional health-history event
- Failure behavior: report not ready

#### `secrets.provider.migrate`

- Owner: Jason Secrets Broker
- Purpose: Migrate approved secrets and metadata between provider adapters.
- State: future
- Governance: exceptional privileged change requiring explicit approval and rollback plan
- Evidence: migration plan, references, verification, cutover, rollback status
- Failure behavior: fail closed; preserve source provider until verified cutover

### 6.3 Governance

#### `governance.action.evaluate`

- Owner: Jason Governance Engine
- Purpose: Evaluate whether a requested capability is allowed, denied, deferred, or requires approval or evidence.
- State: planned
- Governance: constitutional and policy evaluation
- Evidence: request facts, policy versions, decision, rationale reference
- Failure behavior: fail closed

#### `governance.approval.request`

- Owner: Jason Governance Engine
- Purpose: Create a human approval request for a pending governed action.
- State: planned
- Governance: approver-resolution and separation-of-duties policy
- Evidence: request, eligible approvers, status, expiration
- Failure behavior: leave action pending and do not execute

#### `governance.approval.resolve`

- Owner: Jason Governance Engine
- Purpose: Validate and record an approval, rejection, or expiration.
- State: planned
- Governance: approver identity and authority validation
- Evidence: approver identity, decision, timestamp, conditions
- Failure behavior: deny or keep pending

#### `governance.exception.evaluate`

- Owner: Jason Governance Engine
- Purpose: Evaluate a time-limited documented exception and compensating controls.
- State: planned
- Governance: constitutional exception process
- Evidence: exception identifier, approver, expiration, decision
- Failure behavior: deny

### 6.4 Evidence

#### `evidence.record.create`

- Owner: Jason Evidence Store
- Purpose: Create an append-oriented evidence record for an action, decision, approval, deployment, or verification.
- State: planned
- Governance: evidence schema and sensitivity policy
- Evidence: the record itself plus integrity metadata
- Failure behavior: governed state-changing work shall not be reported as complete without required evidence

#### `evidence.record.query`

- Owner: Jason Evidence Store
- Purpose: Query evidence within authorized client, tenant, time, and sensitivity boundaries.
- State: planned
- Governance: audit and data-access policy
- Evidence: query identity, scope, and result count
- Failure behavior: fail closed

#### `evidence.artifact.store`

- Owner: Jason Evidence Store
- Purpose: Store a large artifact centrally and return a governed reference.
- State: planned
- Governance: classification, retention, and client-isolation policy
- Evidence: artifact metadata, hash, owner, retention class
- Failure behavior: do not pass uncontrolled copies between components

#### `evidence.integrity.verify`

- Owner: Jason Evidence Store
- Purpose: Verify integrity metadata for records or artifacts.
- State: planned
- Governance: operational or audit use
- Evidence: verification request and outcome
- Failure behavior: flag the evidence as untrusted and escalate

### 6.5 Events

#### `events.event.publish`

- Owner: Jason Event Bus
- Purpose: Publish a validated, versioned domain event.
- State: planned
- Governance: producer identity, schema, tenant boundary, and sensitivity policy
- Evidence: event identifier, producer, type, routing outcome
- Failure behavior: bounded retry; dead-letter and escalate when exhausted

#### `events.subscription.manage`

- Owner: Jason Event Bus
- Purpose: Create, update, suspend, or retire an approved event subscription.
- State: planned
- Governance: privileged platform configuration
- Evidence: requester, subscriber, event types, filters, change outcome
- Failure behavior: retain last known valid subscription configuration

#### `events.deadletter.reprocess`

- Owner: Jason Event Bus
- Purpose: Reprocess a dead-lettered event after authorization and root-cause review.
- State: planned
- Governance: privileged; approval may be required
- Evidence: original event, reason, requester, remediation, outcome
- Failure behavior: preserve original event and attempt history

### 6.6 Deployment

#### `deployment.release.validate`

- Owner: Jason Deployment System
- Purpose: Validate a release manifest, dependencies, configuration, policy, and rollback readiness.
- State: planned
- Governance: deployment policy
- Evidence: release, checks, policy versions, result
- Failure behavior: block deployment

#### `deployment.release.deploy`

- Owner: Jason Deployment System
- Purpose: Perform a deterministic approved deployment.
- State: planned
- Governance: environment and change-approval policy
- Evidence: requester, approval, release, target, steps, result
- Failure behavior: stop safely and invoke documented rollback when required

#### `deployment.release.rollback`

- Owner: Jason Deployment System
- Purpose: Restore a previously verified release or configuration.
- State: planned
- Governance: rollback policy; emergency path may apply
- Evidence: reason, requester, source and target versions, verification
- Failure behavior: escalate immediately and preserve forensic state

#### `deployment.release.verify`

- Owner: Jason Deployment System
- Purpose: Verify service health, readiness, version, and acceptance checks after deployment.
- State: planned
- Governance: deployment verification policy
- Evidence: checks, observations, result
- Failure behavior: mark deployment unsuccessful and evaluate rollback

### 6.7 Orchestration

#### `orchestration.capability.invoke`

- Owner: Jason Central Orchestrator
- Purpose: Accept a named capability request and coordinate routing, identity, policy, context transfer, approvals, retries, timeouts, evidence, and final result assembly.
- State: planned
- Governance: capability-specific
- Evidence: full orchestration lifecycle metadata
- Failure behavior: fail safely with a structured result

#### `orchestration.artifact.resolve`

- Owner: Jason Central Orchestrator
- Purpose: Resolve an authorized central artifact reference for a capability invocation.
- State: planned
- Governance: artifact and client-boundary policy
- Evidence: requester, reference, purpose, outcome
- Failure behavior: fail closed

#### `orchestration.request.cancel`

- Owner: Jason Central Orchestrator
- Purpose: Cancel a pending or running request when supported by the target capability.
- State: planned
- Governance: requester or operator authority
- Evidence: request, cancelling identity, outcome
- Failure behavior: report whether cancellation was guaranteed or best effort

### 6.8 OpenClaw integration

#### `openclaw.request.submit`

- Owner: OpenClaw Adapter
- Purpose: Translate an authorized OpenClaw operator request into a Jason capability request.
- State: planned
- Governance: operator identity and requested capability policy
- Evidence: operator identity, channel, capability, correlation ID
- Failure behavior: return a clear structured denial or failure

#### `openclaw.approval.present`

- Owner: OpenClaw Adapter
- Purpose: Present a governance approval request to an eligible human operator and return the response to the orchestrator.
- State: planned
- Governance: approver identity and channel assurance
- Evidence: presentation, response, identity, timestamp
- Failure behavior: leave action pending or expire it

OpenClaw remains an operator interface. It is not the source of platform identity, policy, secrets, or evidence truth.

## 7. Initial business capability placeholders

These entries reserve stable business names while their connector specifications are developed.

### Autotask

- `autotask.company.search`
- `autotask.ticket.read`
- `autotask.ticket.create`
- `autotask.ticket.update`
- `autotask.ticket.note.add`
- `autotask.configuration_item.search`

### IT Glue

- `itglue.organization.search`
- `itglue.document.read`
- `itglue.document.create`
- `itglue.flexible_asset.read`
- `itglue.attachment.store`

### Datto RMM

- `datto_rmm.device.search`
- `datto_rmm.device.read`
- `datto_rmm.component.run`
- `datto_rmm.alert.read`

### Microsoft

- `microsoft.user.search`
- `microsoft.user.disable`
- `microsoft.session.revoke`
- `microsoft.group.membership.read`
- `microsoft.group.membership.update`
- `microsoft.mail.search`
- `microsoft.calendar.availability.read`

Each placeholder is non-executable until a versioned specification, authorization model, governance policy, evidence contract, and adapter implementation are approved.

## 8. Capability lifecycle

Capabilities progress through:

1. proposed;
2. approved;
3. implemented;
4. testing;
5. active;
6. deprecated;
7. retired.

Breaking changes require a new capability version. Deprecated versions must identify their replacement and support period.

## 9. Review and stewardship

The Technology Steward shall review the catalog at least quarterly and when a dependent platform announces material API, authentication, licensing, deprecation, or native-capability changes.

Every custom capability shall retain its business justification and retirement criteria. Capabilities shall be simplified or retired when a dependable platform-native function can replace custom implementation without weakening Jason's constitutional guarantees.
