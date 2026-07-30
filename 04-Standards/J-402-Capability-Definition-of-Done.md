# J-402 — Capability Definition of Done

**Status:** Active standard  
**Owner:** Jason Architecture Authority

A Jason capability is not complete merely because it returns a result. Completion requires the capability to be governable, testable, supportable, explainable, and transferable.

## Required completion evidence

### Purpose and ownership

- Capability ID, purpose, steward, review interval, and retirement criteria are recorded.
- The organizational outcome and intended users are explicit.
- Native approved platform capabilities were considered before custom implementation.

### Contracts

- Versioned machine-readable input and output contracts exist.
- Required and optional fields are distinguished.
- Compatibility and deprecation behavior are documented.
- Provider-specific data is normalized before entering core reasoning.

### Identity, authority, and isolation

- Requester, organization, tenant, client, and correlation context are established.
- Maximum authority and approval requirements are enforced.
- Cross-client access tests pass.
- Missing or indeterminate authority fails closed.

### Evidence and reasoning

- Material statements cite evidence references.
- Observation, inference, hypothesis, recommendation, and outcome remain distinct.
- Provenance, collection time, source time, and integrity metadata are preserved where applicable.
- Unsupported confidence and fabricated facts are rejected by deterministic gates.

### Workflow and resilience

- States and legal transitions are explicit.
- Retries, timeouts, pauses, escalation, rejection, and degraded modes are defined.
- Terminal states cannot silently resume.
- Duplicate invocation and replay behavior are tested.

### Communication

- Technician-facing output uses progressive disclosure.
- Uncertainty, missing information, risk, approval needs, and verification steps are visible.
- Sensitive information is limited to authorized need-to-know.

### Security

- Untrusted content is treated as data rather than instruction.
- Secrets and credentials are neither returned nor logged.
- Input size, type, and schema validation are enforced.
- Dependency and static-analysis checks have no unresolved critical findings.

### Audit and memory

- Significant decisions and transitions produce attributable audit records.
- Evidence references, policy versions, model/provider versions, and correlation IDs are retained.
- Outcome feedback can be recorded without rewriting historical evidence.
- Learning candidates cannot become approved knowledge automatically.

### Testing

- Unit, contract, quality-gate, failure, isolation, and end-to-end tests pass.
- At least one representative fixture and one adversarial fixture exist.
- Tests are deterministic and run in continuous integration.
- The capability's success and safety metrics can be measured.

### Operations

- Installation, configuration, health, rollback, and troubleshooting instructions exist.
- Logs are structured and contain no prohibited data.
- A named human owner can support the capability.
- Removal or replacement can occur without destroying required records.

## Approval rule

A capability may enter pilot only after all mandatory items are satisfied or a time-bounded, owner-approved exception is recorded. It may not gain execution authority while material identity, isolation, evidence, quality-gate, or audit requirements remain incomplete.
