# Provider-Neutral Approval Request Foundation

## Status

Foundation implementation. Microsoft Teams is the first channel binding, not an authority source.

## Architectural rule

An approval is a Jason governance object. A delivery channel may display an approval request and return authenticated response metadata, but the channel cannot grant authority, determine policy, change tenant scope, extend expiration, or authorize a capability.

The Central Orchestrator remains responsible for accepting an approval into an execution path. Acceptance requires Jason-controlled validation of organization/client context, authenticated approver identity, approver authorization, requested capability and mode, expiration, evidence references, and approval state.

## Provider-neutral objects

`ApprovalRequest` binds an approval ID and original request ID to correlation, organization/client, requester, capability, requested mode, validity window, authorized approver identities, and immutable evidence references.

`ApprovalResponse` carries only a channel-returned decision plus an identity established by the governed ingress boundary. User-editable channel fields must never be treated as identity proof.

`AcceptedApproval` is emitted only after Jason authority validation. It is designed to be converted/persisted into JKD-001's formal approval repository before a new authority evaluation can issue an execution context.

## Evidence

Approval evidence is passed by immutable artifact reference: artifact ID, organization ID, and SHA-256 integrity digest. Raw artifacts are not copied into channel payloads or passed between agents. Cross-organization evidence references fail closed.

## Microsoft Teams binding

The initial Teams adapter renders non-secret approval metadata and artifact IDs. A Teams response is translated into the provider-neutral `ApprovalResponse`. The approver identity must be supplied by authenticated Microsoft/Entra ingress; it is never accepted from Adaptive Card input.

Teams therefore acts only as:

- delivery surface;
- human interaction surface;
- response transport.

Teams does not become:

- policy authority;
- identity authority;
- approval authority;
- capability authority;
- tenant authority.

## Fail-closed behavior

Responses are rejected when the request is absent, not pending, expired, cross-organization, returned by an unlisted approver, or denied by Jason's authority checker. A deny response is recorded as denied and never converted into execution authority.

## Next integration slice

1. Bind `ApprovalAuthorityChecker` to JKD-001 durable identity/grant state.
2. Persist accepted approvals as JKD-001 `ApprovalRecord` objects rather than treating connector state as authoritative.
3. Add a governed Microsoft/Entra response-ingress verifier that supplies the authenticated Jason identity.
4. Add Central Orchestrator lookup so approval-required execution resumes only after exact-scope JKD-001 validation.
5. Add durable audit events for request creation, channel delivery, response receipt, rejection, expiration, acceptance, and execution consumption.
6. Perform host/live Teams validation only after the Microsoft credential/consent boundary is approved; backend tests remain no-network.
