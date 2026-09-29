## Organizational outcome

Describe the operational problem and the measurable result this change supports.

## Scope

- Capability or service:
- Client/tenant impact:
- Maximum operating mode:
- Provider dependencies:

## Governance and risk

- [ ] Human authority remains explicit.
- [ ] Client isolation is preserved and tested.
- [ ] Provider-specific behavior remains behind an adapter.
- [ ] External content is treated as untrusted data.
- [ ] Evidence, provenance, and audit behavior are documented.
- [ ] Failure and degraded behavior fail safely.
- [ ] No agent invokes or communicates with another agent directly.

## Contracts and compatibility

List schemas, APIs, events, states, or transitions changed. Describe compatibility and migration behavior.

## Integration coordination

- Branch baseline SHA:
- Current-main reconciliation performed:
- Integration coordination: none
- Integration automation: disabled
- Production-impacting change: yes/no
- Intended production release candidate: not selected until merged

List any active PRs that touch the same implementation-sensitive files using PR references such as `#123`. The protected integration gate requires current `main` to be incorporated and active overlaps to be explicitly reviewed. Set `Integration automation: enabled` only for a trusted, reviewed PR that may be automatically reconciled with current `main`, revalidated, and merged when every required gate passes. This never authorizes production deployment.

## Autonomous repair release

Complete only when requesting J-CHANGE-002 autonomous repair classification.

- Release class: normal
- Support item:
- Previously approved behavior:
- New capability: no
- Security impact: none
- New authority or permission: no
- Provider/API contract change: no
- Schema or migration: no
- New dependency: no
- Infrastructure or topology change: no
- Client scope expansion: no
- Disruptive operational behavior: no
- Regression test:
- Post-deploy verification:

Use `Release class: autonomous-repair-candidate` only for a currently open `SUPPORT-*` defect that restores previously approved behavior. Any uncertain answer routes the release back to normal human approval.

## Verification

- [ ] Unit tests
- [ ] Contract tests
- [ ] Isolation/adversarial tests
- [ ] End-to-end fixture
- [ ] Documentation build

Provide the commands and results.

## Reversibility and retirement

Describe rollback, data preservation, custom-code justification, review interval, and retirement criteria.

## Documentation impact

Select exactly one outcome:

- [ ] Documentation updated
- [ ] No documentation impact

No-documentation-impact reason: Not applicable when documentation was updated.

Impact areas reviewed:

- [ ] Architecture / standards / ADRs
- [ ] Component / capability / provider contracts
- [ ] Reusable construction guidance
- [ ] System Registry
- [ ] Operations / runbooks
- [ ] Proof / session evidence
- [ ] Current resume point

## Documentation and decisions

- [ ] ADR added or updated when an enduring decision changed
- [ ] J-402 Definition of Done reviewed when capability maturity changed
