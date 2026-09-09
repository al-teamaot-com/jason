# CAP-001 — Provider Pilot Foundation

**Version:** 0.1
**Status:** Foundation in progress
**Owner:** Jason Architecture Authority
**Applies to:** Read-only provider-backed evidence collection for CAP-001

## 1. Purpose

This increment prepares CAP-001 for a controlled provider-backed pilot without granting operational authority or coupling the capability to one vendor API.

The first boundary is a provider-neutral ticket evidence collector. It accepts the authorized ticket identity already present in the CAP-001 request, calls one named read-only ticket gateway, validates the returned identity and client scope, and converts the result into the existing CAP-001 evidence contract.

## 2. Architectural Boundary

```text
CAP-001 request
    -> governed Kernel resolution
    -> provider-neutral ticket evidence collector
    -> named read-only ticket gateway
    -> normalized immutable evidence record
    -> existing CAP-001 case package
```

The collector does not authenticate directly, select credentials, resolve providers, call another agent, or perform provider writes. Those responsibilities remain outside the capability and under the orchestrator, Kernel, secrets broker, and approved gateway implementation.

## 3. Provider Ticket Contract

A provider ticket record must supply:

- provider ticket identity;
- canonical client identity;
- title and description;
- creation timestamp;
- optional update timestamp;
- optional configuration-item identity;
- optional requester identity.

The collector must reject the result when required fields are missing, the provider differs from the requested provider, the returned ticket identity differs, or the returned client identity crosses the authorized client boundary.

## 4. Evidence Contract

A successful collection emits one evidence record containing:

- deterministic evidence identity;
- provider source;
- collection timestamp;
- title and description summary;
- provider content reference;
- SHA-256 digest of the canonical ticket payload;
- client identity;
- `trusted_as_instruction: false`.

Ticket content is always treated as untrusted data. It cannot change authority, policy, routing, provider selection, or system behavior.

## 5. Initial Provider Boundary

The initial intended gateway is Autotask ticket read access. This increment defines the contract only and uses test gateways. Live Autotask credentials and client data are not required and must not be introduced until the gateway is separately approved and configured through the normal secrets and provider-governance process.

Datto RMM and IT Glue evidence remain separate future adapters so each provider can be reviewed, tested, and retired independently.

## 6. Failure Behavior

The collector fails closed when:

1. the configured gateway does not match the requested provider;
2. the gateway returns another ticket identity;
3. the gateway returns another client identity;
4. required ticket fields are missing;
5. the provider call fails.

No partial or guessed evidence is returned after a failed boundary check.

## 7. Acceptance Criteria

The foundation is complete when:

1. the provider-neutral ticket record is explicit and deterministic;
2. one read-only gateway call is client scoped;
3. returned client and ticket identities are independently verified;
4. provider content is marked untrusted as instruction;
5. canonical payload integrity is represented by SHA-256;
6. tests cover successful collection and each fail-closed boundary;
7. existing CAP-001, Kernel, release, and strict documentation validations pass.

## 8. Deferred Scope

This increment does not include:

- live Autotask credentials;
- Autotask write operations;
- attachment retrieval;
- ticket-note expansion;
- Datto RMM or IT Glue evidence;
- provider retries or caching;
- autonomous remediation;
- direct agent-to-agent communication.

## 9. References

- `03-Components/Capabilities/CAP-001-Professional-Ticket-Investigation.md`
- `03-Components/Kernel/JKD-007-Governed-Capability-Resolution-Engine.md`
- `04-Standards/J-401-Adaptive-Build-Method.md`
- `04-Standards/J-402-Capability-Definition-of-Done.md`
- `04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md`
