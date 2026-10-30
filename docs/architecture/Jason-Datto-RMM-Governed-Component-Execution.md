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



## Failure-class correction evidence (2026-10-30, preproduction)

- **Observed symptom:** a correctly identified, owner-approved `Change Hostname [WIN]`
  quick-job request on an eligible workstation was rejected **before Datto was
  contacted**: `component variable is not approved by the allowlist`.
- **Failure class:** catalog-visible and owner-approved component actions can
  lack a consistent reviewed variable contract at execution-plan preparation;
  runtime policy and provider component semantics may drift independently.
- **Violated invariant:** authority and component discovery do not by
  themselves authorize unspecified variables or a different concrete plan.
  The safe request must have a reproducible, exact, bounded parameter contract.
- **General correction:** reusable source-declared `SourceComponentContract`
  registry and one shared validator, independent of endpoint, ticket or
  conversation text; exact provider UID/name binding; fail-closed input and
  identity checks; retain separate human and provider authority.
- **Regression diversity:** unrelated hostname, backup-log and event-log
  inputs exercise boolean restrictions, validated Windows names, literal
  searches, length/range limits and an unrelated synthetic future component.
  Both UID and name mismatches must fail even for a previously accepted field.
- **Operational state:** draft source only. There has been no provider job, no
  staged rename, no reboot and no production approval expansion under this
  correction. Additional script safety and provider-backed acceptance are
  still required.

## Source-controlled component input validation (preproduction engineering pattern)

**Status:** Implemented in draft source only, pending safety review, provider-backed
acceptance, protected integration and exact-SHA release authorization. This
section does not claim a production activation or standing-safe classification.

The canonical `automation.component.execute` capability continues to use the
Central Orchestrator's per-action identity, approval, client and device scoping,
execution-plan binding, idempotency, and output readback. The Datto adapter's
input validator is a separate **conservative safety contract**, not a source of
human authority. It must not grant a new capability or imply that a component
is certified read-only.

To add one *reviewed* component with sensitive input parameters:

1. Resolve its current UID, name, category, variables and script behavior
   through governed Datto discovery. Do not infer execution safety from a
   component title, description or a previous approval record.
2. Record the selected canonical capability, expected result, risk, target
   classes, per-run/standing-safe classification and owner decision in the
   existing workstream or approval record.
3. Define the reviewed, **provider-specific** variable constraints as a
   declarative `SourceComponentContract` in
   `implementation/connectors/datto_rmm/source_component_contracts.py`.
   Bind the contract to the exact Datto UID **and** display name. No per-client,
   device, ticket or user identifiers belong in this source registry.
4. Use the shared `ComponentVariablePolicy` validator, which supports bounded
   scalars, selection enumerations, booleans (including permitted literal
   values), safe Windows hostnames, and bounded literal search terms. Do not
   introduce a new conditional per component or special-case error message
   into the provider transport.
5. Fail closed for any partial UID/name collision, missing/unknown variables,
   unsupported values, runtime variable-policy override, or metadata drift.
   The source-owned contract takes precedence over generic runtime field
   policy for an exact reviewed identity.
6. Add deterministic tests demonstrating the normal request shape, invalid
   inputs, arbitrary-variable injection, cross-identity drift, and at least one
   unrelated synthetic component using the same general validation mechanism.
7. Separately verify runtime execution scope, dedicated provider execution
   identity, Datto API Component Level, explicit approval where required,
   exact plan fingerprint and job result/readback. Prepare source against
   current protected `main`; use the normal Production Manager release lane.

Initial contracts from owner-authorized issue
[`#2174`](https://github.com/al-teamaot-com/jason/issues/2174)
include non-reboot Windows hostname staging, bounded Endpoint Backup
error-log retrieval and bounded Windows event-log search. The no-reboot
contract allows `usrReboot=false` **only**. It never approves a subsequent
reboot, a security-service restart, or BackupIQ asset deletion. Any future
reboot must use a different action and obtain its own exact authorization.

**Construction example:** `source_component_contracts.py` and
`implementation/connectors/tests/test_datto_owner_2174_variable_contracts.py`.
**Release boundary:** component variable contracts are not equivalent to
activation of the corresponding component on Jason or in Datto's API Component
Level. No production grant, Datto job, or endpoint change is authorized
merely by merging this source code. Documentation must distinguish intended
state from observed production evidence.
