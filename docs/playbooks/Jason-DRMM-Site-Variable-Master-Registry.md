# Jason - DRMM Site Variable Master Registry and New-Site Convergence

## 1. Section Goal

Jason shall maintain an AOT-wide, value-free master registry of Datto RMM site-variable names by polling every authorized DRMM site, and shall use only the human-approved Standard subset to plan creation of missing variable names for a newly onboarded DRMM site.

Success requires proof that:

- all authorized DRMM sites were enumerated;
- every site was scanned or explicitly recorded as failed;
- no secret variable values are persisted in the registry artifact;
- normalization detects case/whitespace variants without silently merging or renaming provider objects;
- discovery never automatically promotes a variable to Standard;
- new-site convergence creates only missing approved Standard names;
- existing site variables are never overwritten by this playbook;
- newly created variable values are blank unless a later separately approved playbook populates them;
- any naming conflict, incomplete scan, authority failure, or unavailable write capability blocks convergence and is documented.

## 2. Trigger

Two deterministic triggers apply.

**Registry Discovery Trigger**

Run when:

- an administrator requests a master DRMM site-variable inventory;
- the approved registry is stale according to policy;
- onboarding requests convergence but no current complete registry exists;
- a material DRMM site-variable standard change requires a refreshed inventory.

**New-Site Convergence Trigger**

Run when:

- a client onboarding workflow has created and authoritatively identified the new Datto RMM site; and
- a current complete registry exists; and
- AOT has an approved Standard variable set.

## 3. Scope and Boundaries

In scope:

- Datto RMM managed-site enumeration;
- Datto RMM site-variable name and configured-status reads;
- normalization for analysis;
- master registry generation;
- human-governed variable classification;
- comparison of a new site against the approved Standard subset;
- planning/creation of missing Standard variable names with blank values when the governed create capability is active and authorized.

Out of scope:

- disclosing secret values to unauthorized requesters;
- persisting variable values in the master registry;
- automatically deciding that a discovered variable is Standard;
- automatically renaming or deleting existing variables;
- overwriting existing values;
- populating client-specific values;
- borrowing values from another client;
- direct Datto provider access outside Central Orchestrator.

Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, approval rules, audit trail, and `direct_provider_access=false`.

## 4. Initial Identification

For registry discovery identify:

- Datto RMM account/provider;
- complete authorized site collection;
- site UID and site name for every site;
- source correlation ID for site enumeration;
- source correlation ID for each site-variable read.

For new-site convergence identify:

- exact client;
- exact onboarding project/task if present;
- exact Datto RMM site UID;
- exact approved Standard registry version;
- current variables on the new site.

If site identity is uncertain, set `state = identification_blocked` and stop.

## 5. Expected State

**Registry**

A complete snapshot exists representing all authorized DRMM sites. Each logical variable name includes:

- canonical display spelling;
- normalized comparison key;
- observed spelling variants;
- site-count coverage;
- configured-site count;
- coverage percentage;
- candidate-standard flag;
- naming-collision flag;
- human-governed disposition.

No provider variable value is stored in the registry.

**New Site**

Every variable classified and approved as Standard exists exactly once by the approved name. Existing values remain untouched. Missing Standard variables are present with blank values until later population/validation.

## 6. State Model

`identified -> enumerating_sites -> reading_variables -> building_registry -> awaiting_standard_review -> registry_approved -> comparing_new_site -> awaiting_write_capability -> creating_missing_names -> verifying -> complete`

Exceptional states:

- `identification_blocked`
- `registry_incomplete`
- `naming_conflict`
- `authority_blocked`
- `write_capability_blocked`
- `escalated`

Persist registry version, scan timestamp, total site count, scanned site count, failed sites, correlation IDs, approved classifications, target site UID, planned creates, completed creates, and verification evidence.

## 7. Diagnostic Workflow

### A. Enumerate Sites

Purpose: prove the complete authorized DRMM site population.

Evidence source: Datto RMM via `management.site.search`.

Expected result: bounded complete site list with durable site UIDs.

Decision:

- complete -> continue;
- incomplete/error -> `registry_incomplete`.

### B. Read Variables for Every Site

Purpose: identify all variable names in current operational use.

Evidence source: Datto RMM via `management.site.variable.list`.

Use only name and configured-status for registry aggregation. Do not persist values.

Expected result: successful read for every authorized site.

Decision:

- all sites succeed -> build registry;
- any site fails -> retain failure evidence and set `registry_incomplete`.

### C. Normalize and Aggregate

Purpose: identify equivalent spelling/case/whitespace variants without changing provider state.

Normalization: trim leading/trailing whitespace, collapse internal whitespace for comparison only, and compare case-insensitively.

Record naming collisions rather than silently merging provider objects.

### D. Standard Review

Purpose: separate observed reality from approved AOT standard.

Discovery may mark high-coverage variables as `candidate_standard`, but only human governance may assign:

- Standard
- Client-Specific
- Legacy
- Deprecated

Unreviewed remains Unreviewed.

### E. Compare New Site

Purpose: determine which approved Standard variable names are missing.

Evidence source: current target-site variable read plus approved registry.

For each approved Standard:

- exact name exists -> satisfied;
- case/whitespace variant exists -> conflict, do not duplicate;
- absent -> plan create with blank value;
- registry collision exists -> conflict, stop that item.

## 8. Decision Gates

Before registry approval:

- all authorized sites enumerated;
- all required site-variable reads completed;
- no secret values persisted;
- naming collisions identified;
- human reviewer approves Standard classifications.

Before new-site mutation:

- target site UID authoritatively resolved;
- complete current registry exists;
- Standard classifications approved;
- current target-site variables re-read immediately before mutation;
- create capability is ACTIVE and action-enabled;
- requester/playbook authority permits the mutation;
- no conflicting variant exists;
- no existing variable will be overwritten.

## 9. Remediation

### Create Missing Standard Variable Name

Operation: `management.site.variable.create`

Target: exact onboarding site UID.

Input:

- approved Standard variable name;
- blank value;
- approved masked setting;
- reason identifying onboarding baseline creation.

Authority classification: modifying, non-disruptive.

Rules:

- never update an existing value in this playbook;
- never create from Candidate Standard alone;
- never create when naming collision exists;
- never create a client-specific, legacy, deprecated, or unreviewed variable;
- mutation must be idempotent against target site + normalized approved name + registry version.

Current implementation limitation: live Jason currently exposes `management.site.variable.list` but does not expose an action-enabled `management.site.variable.create`. Until that capability is activated, convergence must stop at `write_capability_blocked` with the exact planned creates preserved.

## 10. Retry Policy

Read operations: maximum two attempts per provider read when failure is transient and retry is safe.

Registry scan: do not silently omit a failed site. A failed site keeps the registry incomplete.

Create operation: one create submission per approved variable per convergence generation. A readback failure does not authorize redispatch. Re-read before any retry.

## 11. Periodic Rechecks

Registry refresh cadence should be configurable. Default recommendation: refresh before each client onboarding convergence and additionally on a scheduled governance cadence.

Do not schedule duplicate scans for the same registry generation.

New-site convergence may recheck when:

- write capability becomes active;
- a naming conflict is resolved;
- the approved Standard set changes.

## 12. Aging / Stale Condition

A registry is stale when any of the following is true:

- policy-defined maximum age is exceeded;
- a material site-variable standard change occurs;
- DRMM site inventory materially changes;
- onboarding requests convergence and the last complete scan predates the approved Standard revision.

A stale registry cannot authorize new-site convergence.

## 13. Dependency Handling

Dependencies include:

- active `management.site.search`;
- active `management.site.variable.list`;
- persisted registry storage/versioning;
- human Standard classification;
- active/action-enabled `management.site.variable.create` for mutation;
- onboarding-to-DRMM-site authoritative association.

Missing mutation capability does not invalidate discovery. Persist the plan and block mutation.

## 14. Documentation Requirements

For registry discovery record:

- scan timestamp;
- total sites;
- scanned sites;
- failed sites;
- unique logical variable count;
- naming-collision count;
- candidate-standard count;
- source correlation IDs;
- registry version/hash.

Do not record secret values.

For convergence record:

- target client/site;
- registry version;
- approved Standard count;
- already-present count;
- missing count;
- conflicts;
- exact variable names planned/created;
- mutation correlation IDs;
- readback verification.

Suggested titles:

- `Jason - DRMM Site Variable Registry - Discovery`
- `Jason - DRMM Site Variable Registry - Standard Review`
- `Jason - DRMM Site Variable Registry - New Site Comparison`
- `Jason - DRMM Site Variable Registry - Convergence`
- `Jason - DRMM Site Variable Registry - Verification`
- `Jason - DRMM Site Variable Registry - Escalation`

## 15. Failure Handling

Fail closed for:

- incomplete site enumeration;
- failed site-variable read;
- unexpected provider payload;
- duplicate logical names on one site;
- case/whitespace naming collision;
- stale registry;
- missing Standard approval;
- unauthorized requester;
- unavailable create capability;
- mutation error;
- contradictory readback.

Never fall back to direct provider access or shell/API bypass.

## 16. Escalation Criteria

Escalate when:

- registry cannot be completed after bounded reads;
- naming collision requires standardization decision;
- approved Standard is absent from discovered master inventory;
- target site identity is ambiguous;
- mutation capability remains unavailable;
- provider rejects creation;
- readback disagrees with expected state;
- proposed action would overwrite or disclose an existing value.

## 17. Verification

Registry verification requires:

- site count from discovery equals expected scan population;
- scanned-sites count equals total-sites count;
- failed-sites list is empty;
- registry contains no values/secrets.

New-site verification requires authoritative target-site re-read proving every approved Standard variable name exists once. Do not require values to be populated; value population belongs to a later onboarding task.

## 18. Completion Criteria

**Registry Discovery Complete**

- all sites scanned;
- registry built;
- collisions surfaced;
- no secret values persisted;
- human classification recorded.

**New-Site Convergence Complete**

- target site identified;
- current approved registry used;
- all Standard variable names present;
- no existing values overwritten;
- creates verified by readback;
- conflicts resolved or formally escalated;
- documentation complete.

## 19. Final Resolution Note

Summarize registry version, scan size, Standard count, target site, already-present names, created names, unresolved conflicts, verification timestamp, and disposition. Never include variable values.

## 20. Required Capabilities

Currently available:

- `management.site.search`
- `management.site.variable.list`

Required for full convergence:

- `management.site.variable.create` as an active governed, action-enabled capability
- persisted registry/version storage
- onboarding project/site association
- audit/event persistence

Optional later capability:

- `management.site.variable.update` for the separate population/validation playbook, not this playbook.

## 21. Acceptance Test

1. Enumerate the complete authorized DRMM site list.
2. Read site variables from every site.
3. Build a value-free master registry.
4. Demonstrate high-coverage variables remain Candidate/Unreviewed until human approval.
5. Demonstrate case variants are reported as conflicts.
6. Select a controlled new/test DRMM site.
7. Compare against a small approved Standard set.
8. Verify existing names are preserved.
9. Verify only missing names are planned with blank values.
10. If create capability is active, create one controlled missing variable and verify readback.
11. If create capability is unavailable, prove deterministic `write_capability_blocked` behavior without provider bypass.
12. Confirm no variable value is written to logs, ticket notes, registry artifacts, or user-visible output.

## 22. Section Goal Closure

Close only after:

- source implementation is committed;
- unit tests pass;
- complete live read-only registry scan is demonstrated;
- human Standard-review mechanism is documented;
- one controlled new-site convergence acceptance test succeeds after governed create activation;
- limitations and follow-up TODOs are recorded.
