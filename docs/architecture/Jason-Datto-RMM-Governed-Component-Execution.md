# Jason Datto RMM Governed Component Execution

**Status:** Initial design/workstream start  
**Date:** 2026-09-14  
**Production impact:** None. This document does not enable writes or component execution.

## Objective

Add governed Datto RMM component execution to Jason while preserving the existing provider-neutral architecture, identity-first authorization, client/device scoping, approval controls, auditability, rollback discipline, and least privilege.

The first supported action is a Datto RMM quick job against one verified endpoint. Read-only supporting capabilities for component/job inspection should be added before live execution so Jason can deterministically identify what may run and verify the resulting job.

## Existing foundation

Jason already contains a mutation-planning boundary in `implementation/connectors/datto_rmm/mutations.py` with `datto_rmm.component.run` classified as high risk. It already requires:

- a durable device UID;
- a component UID;
- an approved component allowlist name;
- a human-readable reason;
- idempotency for execution;
- approval for execution;
- audit events;
- propose-vs-execute separation.

Live Datto mutation execution is intentionally disabled today. The current mutation connector raises `Datto RMM live mutation executor is not configured.` for any non-proposal attempt.

The kernel authority model already distinguishes `OBSERVE`, `RECOMMEND`, `REQUEST_APPROVAL`, `EXECUTE`, and `ADMINISTER`. Component execution must use `EXECUTE`; existing Datto reads remain `OBSERVE`.

## Vendor contract

Current Datto RMM API v2 documentation identifies the quick-job operation as:

- `PUT /v2/device/{deviceUid}/quickjob`

The endpoint requires, at minimum, Datto permissions equivalent to:

- Sites: View;
- Devices: Manage and View;
- Active Jobs: Manage;
- Components: View;
- access constrained by Device Visibility;
- access constrained by API Component Level.

Successful quick-job creation returns a job UID. Datto exposes read-only job endpoints under `/v2/job/*`; `GET /v2/job/{jobUid}` can be used to determine whether the job is active or completed. Current vendor documentation also exposes account component records through `GET /v2/account/components`, subject to API Component Level.

Reference: `https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm`

## Credential separation

Do **not** broaden the existing `datto_rmm.readonly` credential into a write-capable identity.

Introduce a separate logical secret/identity for execution, for example:

- `datto_rmm.readonly` — existing governed read identity;
- `datto_rmm.execution` — new least-privilege identity used only for explicitly authorized action capabilities.

The Datto execution API user should have the minimum Security Level, Device Visibility, and API Component Level necessary for the approved component set. The API Component Level is an important provider-native containment layer and should be treated as a second allowlist in addition to Jason's own allowlist.

## Initial capability model

### Read-only supporting capabilities

These may use the normal observe path and the read-only credential where provider permissions allow it:

1. `automation.component.search`
   - provider mapping: Datto account component inventory;
   - purpose: locate components by human-readable name and obtain provider identity internally;
   - no execution authority implied.

2. `automation.job.read`
   - provider mapping: Datto job read/status;
   - purpose: read current job state after creation;
   - no execution authority implied.

3. `automation.job.components.read` (only if useful after API-contract inspection)
   - provider mapping: components associated with a Datto job;
   - purpose: verification/audit.

Provider IDs remain internal unless needed for troubleshooting/audit. User-facing output should prefer component names, endpoint names, job status, timestamps, and bounded result summaries.

### Action capability

Canonical capability:

- `automation.component.execute`

Provider mapping:

- `datto_rmm.component.run`
- `PUT /v2/device/{deviceUid}/quickjob`

The canonical capability must not expose Datto as Jason's ontology. Datto is the current implementation provider for AOT.

## Action safety model

A component execution request must fail closed unless all of the following are true:

1. Caller identity is verified and mapped to an active Jason principal.
2. Principal has `EXECUTE` authority for the canonical component-execution capability and the target client/device scope.
3. The endpoint selector resolves to exactly one provider-returned durable endpoint identity.
4. Device/client association is reconfirmed immediately before execution.
5. The component resolves to exactly one allowlisted component identity.
6. Component is present in the provider-native API Component Level assigned to the execution identity.
7. Required component variables are schema-validated and bounded.
8. A human-readable reason is present.
9. An idempotency key is present and reserved.
10. Required approval is present, current, single-use where configured, and cryptographically/deterministically bound to the exact argument digest.
11. Jason records pre-execution evidence and audit events.
12. Provider quick-job creation succeeds and returns a job UID.
13. Jason records only the bounded, non-secret job identity/evidence required for later verification.

No capability should allow arbitrary PowerShell, shell, batch, URL, binary, or script text to be supplied at execution time. Jason should run only pre-existing provider components that are explicitly approved.

## Component allowlist

Jason's allowlist should be durable and provider-neutral. Each entry should contain enough information to prove what is authorized without embedding secrets or executable content, for example:

- canonical component identifier;
- approved display name;
- provider implementation mapping (Datto component UID stored internally);
- approved version/revision fingerprint when available;
- risk classification;
- allowed target classes (workstation/server/etc.);
- allowed variables and validation rules;
- whether user notification is required;
- whether explicit per-run approval is required;
- expected outcome/evidence;
- owner and approval date;
- status (`active`, `suspended`, `retired`).

A provider component changing underneath the same human-readable name must not silently inherit authorization. Where Datto exposes enough metadata, pin or fingerprint the approved implementation. If it does not, require explicit re-verification after component changes.

## Role direction

The planned Jason roles should map to capability grants rather than hard-coded provider behavior:

- **Owner:** may be granted component execution and approval authority, subject to normal high-risk controls;
- **Admin:** may be granted component execution but cannot alter constitutional/governance policy by virtue of this capability;
- **Tech:** may be granted component execution on endpoints/clients within authorized scope;
- **RO:** observe-only; cannot request or execute component mutations.

Exact grants belong in durable authority data, not in the Datto connector.

## Approval policy

Initial production policy should be conservative:

- proposal/discovery can occur without changing endpoints;
- every live component execution requires explicit human approval until enough real-world evidence justifies narrower pre-approved classes;
- approval binds to caller, client, endpoint, component, variables, reason, and argument digest;
- approval expires quickly and is single-use;
- no wildcard approval for arbitrary components or arbitrary devices.

A future policy may permit low-risk pre-approved diagnostic components for Tech users without per-run Owner approval, but only after the allowlist, identity, client scope, audit, job verification, and rollback behavior are proven.

## Execution lifecycle

1. **Discover target** through governed endpoint search/read.
2. **Discover component** through governed component catalog read.
3. **Build proposal** through `datto_rmm.component.run` planning boundary.
4. **Return human-relevant proposal**: endpoint, client, component name, variables, expected effect, risk, and reason.
5. **Obtain approval** when required.
6. **Re-resolve/reconfirm** endpoint and component identity immediately before execution.
7. **Reserve idempotency key.**
8. **Execute quick job** through the separate execution credential.
9. **Record returned job UID internally.**
10. **Read job status** through a governed read capability.
11. **Return bounded outcome** without raw provider secrets/implementation noise.
12. **Audit** proposal, approval, execution, provider result, and verification.

## Phase plan

### Phase 1 — Read-only foundation

- verify the exact current Datto OpenAPI request/response schemas for account components, quick jobs, and job status;
- add component catalog search/read support;
- add job status read support;
- add tests for identity resolution, pagination/bounds where applicable, provider-ID concealment, and information-release controls;
- no production write credential and no live execution.

### Phase 2 — Execution connector in test/propose-only mode

- preserve existing `DattoRmmMutationConnector` planning contract;
- add a provider executor abstraction behind it;
- implement deterministic quick-job request construction;
- use a fake transport/test credential only;
- prove allowlist, approval, idempotency, device-scope, variable validation, and audit failures closed;
- still no production execution.

### Phase 3 — Least-privilege Datto execution identity

- create a separate Datto API user/credential;
- assign minimum required Security Level and Device Visibility;
- assign an API Component Level containing only approved components;
- stage the new secret under OpenBao as a separate logical secret;
- prove authentication and harmless read-only permission checks first.

This phase requires owner approval before provider/security changes.

### Phase 4 — Controlled production pilot

- activate exactly one low-risk, reversible diagnostic/read-only component first;
- restrict to Owner initially unless explicitly approved otherwise;
- require per-run approval;
- execute on one designated noncritical test endpoint;
- verify Datto job status/result through governed read;
- preserve full audit evidence and rollback/disable procedure;
- confirm existing reads and security boundaries remain unchanged.

### Phase 5 — Technician rollout

- map Owner/Admin/Tech/RO authority grants;
- enable only approved component classes for Tech;
- maintain client/device scope and provider-native component restrictions;
- add monitoring for execution failures, duplicate submissions, unexpected component drift, and authorization failures.

## Explicit non-goals for the first workstream

- arbitrary command execution;
- arbitrary uploaded scripts;
- unrestricted component library execution;
- site-wide or fleet-wide component runs;
- unattended self-approval;
- changing existing read-only Datto credentials into a write identity;
- enabling reboot/UDF/alert mutation merely because the mutation connector already lists those capabilities;
- provider writes before source tests, least-privilege provider identity, approvals, and rollback are proven.

## First acceptance milestone

The first milestone is complete when Jason can, in source/tests only:

1. search/read the allowed Datto component catalog;
2. read Datto job status;
3. generate a governed component-run proposal for one uniquely resolved endpoint;
4. reject execution without exact `EXECUTE` authority, allowlist membership, reason, idempotency, and approval;
5. construct the correct Datto quick-job request without sending it to production.

Production remains read-only until a later explicitly approved activation step.
