# Jason Autonomous Execution Production Acceptance — 2026-09-25

## Purpose

Record the first successful production provider mutation performed by Project Jason's dedicated autonomous workload identity under the full governed execution stack.

This record proves the **autonomous execution substrate**. It does not grant generic write authority and does not promote any operational remediation playbook.

## Production boundary

At acceptance:

- Central Orchestrator remained authoritative.
- `direct_provider_access=false`.
- Workload identity: `jason-autonomy-worker`.
- Authority source: JKD-001 exact grants.
- Autonomous approval source: durable `PlaybookAutonomyApproval`.
- Execution-plan binding remained fail-closed.
- Provider execution remained single-attempt.
- Independent post-write verification was mandatory.
- All acceptance-specific authority was temporary and revoked after proof.

## Controlled target

A dedicated test ticket was created in XYZ Test Company solely for the acceptance:

- Company: XYZ Test Company
- Company ID: `1158`
- Ticket number: `T20260925.0051`
- Ticket ID: `141233`
- Queue: Jason
- Initial status: New
- Initial priority: Normal
- No endpoint/CI was involved.

A separate human-path control note proved the ticket and Autotask TicketNote endpoint were writable independently of the autonomous identity.

## Identity discovery and attribution

Governed Autotask Resource reads established:

- `29682930` = Jason ReadWrite;
- `29682926` = Jason Read Only;
- `29682899` = Lindsey Collins.

The human-path control note showed:

- `creatorResourceID=29682885` — Al Davis;
- `impersonatorCreatorResourceID=29682930` — Jason ReadWrite.

This proved Resource `29682930` is the Autotask API user used by the write credential.

The final autonomous model therefore uses **direct API-user attribution** for `jason-autonomy-worker` rather than asking the API user to impersonate itself.

## Acceptance path

The successful autonomous action used:

- capability: `service.ticket.note.create`;
- provider: `autotask_internal_note`;
- target path: `POST /V1.0/Tickets/141233/Notes`;
- exact workload principal: `jason-autonomy-worker`;
- exact Autotask creator Resource: `29682930`.

The accepted note:

- note ID: `30509332`;
- title: `Jason - Autonomous Execution Acceptance v2`;
- creator Resource: `29682930`;
- impersonator Resource: null.

The note content explicitly stated that it was a controlled autonomous service-principal acceptance test and that no ticket fields or endpoint state were changed.

## Governed execution evidence

Successful execution:

- execution ID: `exec_autonomy_559d20ebdeaa40f2bb5ccafc4a1cce61`;
- correlation ID: `corr_autonomy_4b0af623d006492b87e2f3d4ca4ed133`;
- approval ID: `approval_mcp_aebd2009640046d782f932ff8d80debd`;
- idempotency key: `idem_mcp_action_2e536a88873d4e0ea70f84737c21d4fc`;
- intent/action fingerprint: `31fe3a9edada5dae203c08c264d8fd766ebf6ece86c71a12b6ef5c0bf301e555`;
- execution-plan fingerprint: `42c98ab374d904f7f5cf46dea9e8c02bb873eeb56549aa435d5dc3630369ae7d`;
- governed execution state: `succeeded`;
- failure reason: null;
- provider attempts: exactly 1.

The execution plan was bound to the exact provider, capability, ticket, normalized path, and normalized payload before provider invocation.

## Verification proof

The connector returned:

- `jasonVerification.readbackVerified=true`;
- `ticketNoteId=30509332`;
- `creatorResourceId=29682930`;
- `impersonatorRecorded=false`.

Independent governed `service.ticket.notes.search` observed the same note ID and attribution.

Provider success alone was not treated as completion.

## Duplicate suppression

A second acceptance run used the same exact marker.

Result:

- existing note recognized;
- acceptance returned the already-verified path;
- duplicate write avoided;
- no second matching provider write occurred.

This proved the acceptance workflow's idempotency/duplicate-suppression behavior.

## Fail-closed defects discovered during acceptance

The production acceptance intentionally exposed and resolved several boundaries before final success.

### Information release boundary

The first autonomous pre-read was denied with `INFORMATION_RELEASE_DENIED`.

Fix:

- added exact `autonomous-execution-acceptance-read-v1` release policy;
- permitted only `service.ticket.read`, `service.company.read`, and `service.ticket.notes.search`;
- required `jason-autonomy-worker`, observe authority, JKD-001 context, and the exact policy;
- added regression coverage preventing reuse for other capabilities or principals.

Merged in PR #325.

### Provider principal binding

The next run was denied with `AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED`.

This correctly exposed that the mutation connector only understood human Microsoft-to-Autotask impersonation.

A scoped internal-note service-principal path was introduced and tested without widening the generic mutation connector.

### API-user self-impersonation

The scoped requester path initially used `ImpersonationResourceId=29682930`.

Autotask returned HTTP 500 on the actual TicketNote POST. No note was created.

The successful human control note then proved Resource 29682930 was already the API user. The autonomous design was corrected to use direct API-user attribution without an impersonation header.

Merged in PR #328.

### Provider result envelope

The first successful autonomous provider write occurred, but the pilot reporting harness initially read verification from the wrong result-envelope level.

The provider result itself already contained successful `jasonVerification` and the durable note was independently visible.

The reporting harness was corrected to read `output.data.jasonVerification`.

Merged in PR #329.

## Security regression and deployment controls

Relevant source changes passed their applicable CI/security workflows, including SEC-007.

Production MCP deployment used:

- exact source-revision image labels;
- normal production preflight;
- mount/env parity checks;
- hardening verification;
- health verification;
- rollback preparation;
- post-deploy governance verification.

Accepted production MCP source checkpoint:

`d3bdf0ced712e6602a46b14ddbaa6e83a139ebc6`

## Cleanup

After proof:

- all acceptance-specific `PlaybookAutonomyApproval` records were revoked;
- all four temporary JKD-001 acceptance grants were revoked;
- no operational playbook was promoted;
- no broad autonomous write grant remains;
- queue processing remains shadow-only.

The temporary acceptance grants had covered only:

- `service.ticket.read` — observe;
- `service.company.read` — observe;
- `service.ticket.notes.search` — observe;
- `service.ticket.note.create` — execute with approval required.

## Operational meaning

Project Jason has now proven that a non-human service identity can:

1. gather exact governed evidence;
2. satisfy information-release policy;
3. resolve current authority;
4. require and consume a durable owner promotion;
5. bind an exact provider execution plan;
6. perform one authorized provider mutation;
7. independently verify the result;
8. suppress a duplicate execution;
9. preserve full audit evidence; and
10. relinquish all temporary authority after acceptance.

This is the substrate required for bounded autonomous MSP operations.

It is **not** permission for Jason to improvise writes or for existing playbooks to become autonomous automatically.

## Next phase

The next phase is controlled testing of the **first real operational playbook**.

Each candidate playbook must be tested and promoted independently for its exact:

- trigger/match conditions;
- playbook version;
- allowed capabilities;
- target scope;
- governance requirements;
- disruptive-action boundary;
- verification method;
- retry/idempotency rules;
- suspension/revocation behavior;
- blast-radius limits.

Until that happens, operational playbooks remain shadow/investigation-only.
