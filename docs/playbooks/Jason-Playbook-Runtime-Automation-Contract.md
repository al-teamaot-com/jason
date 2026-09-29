# Jason Playbook Runtime and Automation Contract

Version: 1.0-design
Status: Proposed shared standard
Reference implementation: `Jason-BackupIQ-Datto-Endpoint-Backup.md`

## Purpose

Jason playbooks must be easy to create, easy to compare, easy to test, and safe to automate.

A new playbook should primarily define domain-specific facts:
- what triggers it;
- what healthy means;
- which evidence answers each question;
- what classifications are possible;
- which remediation belongs to each classification;
- how resolution is proven.

Common workflow machinery must be implemented once by the Jason Playbook Runtime and inherited by every playbook.

A playbook defines operational logic. It never grants execution authority.

All behavior remains subordinate to the Jason Constitution, Central Orchestrator, exact requester grants, provider/client isolation, approval requirements, disruption controls, and `direct_provider_access=false`.

---

## 1. Three-Layer Model

### A. Jason Playbook Runtime

Common automation implemented once:

- trigger admission;
- queue ownership;
- active-work-slot management;
- ticket work-start lifecycle;
- configuration-item/device/user/site association;
- provider/client boundary validation;
- persisted state;
- evidence fingerprints;
- duplicate suppression;
- waiting and scheduled rechecks;
- bounded retries;
- job/correlation tracking;
- authority and disruption gates;
- dependency handling;
- ticket documentation;
- human-review handoff;
- terminal ticket-state readback;
- telemetry/Grafana state.

### B. Jason Standard Playbook Contract

Every playbook declares:

- metadata and version;
- trigger;
- scope;
- ownership policy;
- target object type;
- authoritative evidence sources;
- expected state;
- classifications;
- decision gates;
- remediation branches;
- retry policy;
- recheck policy;
- stale/aging rules;
- verification criteria;
- completion disposition;
- required capabilities;
- autonomy manifest;
- acceptance-test matrix.

### C. Individual Playbook

Only domain-specific knowledge should remain here.

Design rule:

> If a behavior should apply to multiple playbooks, move it into the runtime or standard contract instead of copying it.

---

## 2. Standard Playbook Manifest

Every playbook should begin with a machine-readable conceptual manifest, whether stored as YAML/JSON later or represented in Markdown initially.

Minimum fields:

```yaml
playbook:
  id: <stable_id>
  name: <human_name>
  version: <semantic_version>
  owner: <operational_owner>
  target_type: <ticket|endpoint|user|site|service|provider_object>
  trigger:
    provider: <source>
    match: <exact rule>
  ownership:
    while_open: <Jason|source_queue|conditional>
    release_active_slot_when_waiting: true
  expected_state: <named healthy-state definition>
  classifications:
    - <classification>
  retry:
    max_remediation_attempts: <n>
  recheck:
    enabled: true|false
    cadence: <duration>
    stale_after: <duration>
  verification:
    authoritative_source: <source>
    success_condition: <condition>
  completion:
    terminal_disposition: <Complete|Human Review|other>
  autonomy:
    allowed_branches:
      - <branch>
    approval_bound_branches:
      - <branch>
    disruptive_branches:
      - <branch>
```

The runtime consumes this contract; the playbook does not reimplement runtime mechanics.

---

## 3. Canonical Lifecycle

All playbooks inherit:

`detected -> owned -> identified -> diagnosing -> classified`

Then one of:

- `waiting`
- `blocked`
- `remediating`
- `verifying`
- `human_review`
- `escalated`
- `complete`

Playbook-specific substates may exist, such as:

- `waiting_device`
- `waiting_backup_cycle`
- `waiting_propagation`
- `waiting_approval`
- `configuration_blocked`
- `stale_asset_review`

They must map to the shared lifecycle semantics.

---

## 4. Ownership and Active Work Are Separate

Queue ownership is not the same as active processing.

A playbook may declare an invariant such as:

`Open + matching trigger => Jason queue`

The ticket may remain owned by Jason while:

- the device is offline;
- Jason is waiting for a normal provider cycle;
- a scheduled recheck is pending;
- a non-human dependency is pending;
- the global active-work limit is full.

Active-work limits control only concurrent diagnosing/remediating/verifying work.

Waiting tickets normally release their active slot.

A capacity limit must never accidentally become a queue-routing rule.

---

## 5. Work-Start Gate

Before the first ticket-specific diagnostic, remediation, or verification action, the runtime must complete the global work-start lifecycle.

For Autotask work this normally means:

1. required queue ownership established;
2. Status = In Progress when entering active work;
3. Work Type = Remote Support where applicable;
4. authoritative readback succeeds;
5. transition is persisted.

If this fails, Jason fails closed and does not continue substantive work.

---

## 6. Identity Contract

The runtime performs common identity gates:

1. exact ticket/trigger;
2. exact client/company;
3. exact affected endpoint/user/site/service/provider object;
4. preserve and validate existing CI association;
5. if missing, resolve exactly one same-client active object from authoritative evidence;
6. detect duplicate, renamed, reimaged, replaced, retired, and stale objects;
7. fail closed on ambiguity.

Ambiguous identity:

`state = identification_blocked`

Jason documents candidates and does not guess.

Cross-client evidence never satisfies identity.

---

## 7. Evidence Contract

Each playbook declares which source is authoritative for each question.

The runtime records:

- source;
- target;
- timestamp;
- capability/read/component;
- result;
- job/correlation ID where available;
- interpretation;
- resulting decision.

### Negative evidence

A successful authoritative query returning no object is valid evidence.

Examples:

- no provider asset;
- no active alert;
- no missing patch;
- no running process;
- no matching CI.

An empty authoritative result is not a connector failure.

Connector failure means the read itself failed, was unauthorized, unavailable, or could not be trusted.

---

## 8. Expected-State and Classification Contracts

Every playbook defines healthy state before remediation.

An alert is a symptom, not proof of root cause.

Diagnostics must resolve to a bounded classification.

Each classification maps to one of:

- stale/recovered;
- wait;
- diagnose further;
- remediate;
- dependency blocked;
- human review;
- escalate;
- terminal lifecycle resolution.

The classification and its evidence fingerprint are persisted.

---

## 9. Waiting Is First-Class

Waiting is legitimate operational work.

Typical reasons:

- endpoint offline;
- pending backup cycle;
- pending provider propagation;
- user unavailable;
- maintenance window;
- pending approval;
- scheduled retry/recheck.

Approval waiting is a first-class waiting subtype. An approval-pending playbook instance should retain ownership, release its active-work slot, persist the exact proposed action (target, capability/component, bounded arguments, expected verification, and approval identity when granted), and resume only when that exact action receives valid authority. Approval of one target/action must never authorize another.

When entering waiting, persist:

- reason;
- recheck condition;
- next recheck/cadence;
- stale threshold;
- evidence fingerprint;
- queue ownership;
- active-slot release.

Unchanged rechecks do not create duplicate notes.

When the condition changes, resume from the persisted state rather than restarting.

---

## 10. Idempotence and Duplicate Suppression

The runtime suppresses duplicate:

- notes;
- dependency tickets;
- scheduled rechecks;
- remediation submissions;
- provider writes;
- handoffs;
- terminal transitions.

Persist fingerprints for:

- observed state;
- documented state;
- remediation request;
- active job/correlation ID;
- dependency object;
- terminal disposition.

A repeated unchanged observation is not a new event.

Duplicate suppression is semantic and cross-origin. The deduplication key must not depend on whether the same playbook/state was reached by the autonomous worker, a technician-triggered governed run, a resumed session, or a scheduled recheck. Cosmetic note-title differences must not defeat suppression. Where two actors converge on the same playbook, target, classification/state, and materially equivalent evidence fingerprint within the same state-transition window, the runtime should preserve one authoritative ticket note and record the additional execution only in operational/audit state.

---

## 11. Decision-Gate Stack

Common gates before remediation:

- correct client boundary;
- exact identity;
- required availability;
- required online duration;
- required dependencies;
- no conflicting maintenance/retirement/reimage evidence;
- exact capability exists;
- authority exists for exact action/target;
- disruption policy satisfied;
- no equivalent in-flight action;
- retry limit not exhausted.

Playbook-specific gates are added after these common gates.

No playbook may bypass a failed common gate.

---

## 12. Action Classification

Every action is classified as:

- `read_only`
- `non_destructive`
- `modifying`
- `disruptive`

The playbook states which action is appropriate.

The governance layer decides whether it is authorized.

The playbook never self-authorizes.

---

## 12A. Playbook-Scoped Component Authority

Global component safety and playbook autonomy are separate controls.

A component may remain globally classified `per_run` while one exact playbook branch is approved for autonomous use of that component. This is appropriate when the component is not universally safe, but a narrowly constrained invocation has a well-defined target, arguments, evidence gates, and verification contract.

Playbook-scoped component authority must require all of the following:

- exact Owner-promoted playbook ID and version;
- exact playbook policy ID;
- `automation.component.execute` included in that playbook's approved capability set;
- exact source-controlled component UID and display name;
- exact source-controlled variable contract;
- exact target/client/identity gates from the playbook;
- server-generated/trusted playbook context propagated through Central Orchestrator to the provider;
- provider-side validation of the same playbook/version/policy/component/arguments;
- single-use/idempotent execution binding;
- bounded attempts;
- authoritative post-action verification.

Caller-supplied arguments may never declare or upgrade themselves into playbook-scoped authority.

A playbook-scoped exception must **not** change the component's global Component Control classification. The same component remains approval-bound for interactive use, ad-hoc execution, other playbooks, changed arguments, changed targets, or changed versions.

Reboot, forced logoff, arbitrary shell/PowerShell, destructive actions, and other constitutional disruption classes remain subject to their separate disruption rules even if a playbook is otherwise autonomous.

## 13. Retry Contract

Every remediation branch declares a bounded retry limit.

The runtime owns attempt counting.

A full attempt should be defined by the playbook and normally includes:

- pre-check;
- dependency validation;
- action execution;
- terminal job result;
- post-action diagnostics;
- authoritative verification.

Retries require evidence that another attempt is reasonable.

No infinite loops.

---

## 14. Verification Contract

Action success and incident resolution are separate.

Examples:

- installer exit code 0 != backup restored;
- patch command success != vulnerability resolved;
- service start success != monitoring healthy;
- file deletion success != security incident resolved.

Every playbook declares the authoritative resolution source and condition.

No completion without authoritative healthy-state evidence.

---

## 15. Aging and Lifecycle Contract

Every wait-capable playbook declares:

- normal wait threshold;
- stale-condition threshold;
- lifecycle questions to investigate after that threshold.

Long-running symptoms should eventually be reclassified into lifecycle conditions such as:

- retired;
- replaced;
- stale object;
- duplicate;
- renamed/reimaged;
- decommissioned;
- policy/configuration drift.

Do not retry normal remediation indefinitely against a lifecycle problem.

---

## 16. Human Review Contract

Human review is a deliberate classification, not a generic failure bucket.

Common reasons:

- ambiguous identity;
- policy/business decision required;
- disruptive action required;
- conflicting authoritative evidence;
- retry exhaustion;
- unsupported condition;
- risky lifecycle mutation;
- missing approval-bound dependency.

Handoff must state the exact unresolved decision/action.

---

## 17. Documentation Contract

Jason-authored notes use the common layout:

1. **STATUS**
2. **NEXT STEP** or **ACTION REQUIRED**
3. **WHEN / ESCALATION**
4. **KEY EVIDENCE**
5. **WHAT JASON DID**
6. **CHANGES MADE**
7. **JASON STATE**

The runtime should generate this structure centrally where possible.

Note classes/titles are canonical per playbook state. Autonomous execution must not create a separate note class merely by adding words such as "Autonomous" when the semantic state is the same. Origin/actor belongs in audit metadata, not in the note's semantic deduplication identity.

Meaningful state transitions are documented.

Unchanged polling is persisted operationally but not repeatedly written to the ticket.

Never document secrets.

---

## 18. Completion Contract

A playbook instance is complete only after:

1. target identity is confirmed;
2. required diagnostics are complete;
3. classification/root cause is established;
4. required remediation completed;
5. authoritative resolution evidence exists;
6. documentation is complete;
7. final resolution note exists;
8. terminal PSA/provider write succeeds;
9. terminal state is independently read back.

If terminal readback fails, the playbook is not complete.

---

## 19. Capability Manifest

Every playbook lists the narrowest capabilities required.

Missing capabilities are explicit implementation gaps.

A playbook must not silently fall back to broader shell/provider access.

---

## 20. Branch-Level Autonomy Manifest

Autonomy is granted to exact branches, not entire playbooks.

Example:

```yaml
autonomy:
  allowed_branches:
    - identify
    - classify
    - wait
    - close_recovered
  approval_bound_branches:
    - reinstall_agent
    - change_policy
  disruptive_branches:
    - reboot
```

A source change affecting an autonomous branch requires revalidation and owner review according to Jason governance.

---

## 21. Standard Acceptance-Test Matrix

Every new playbook should test, where applicable:

1. correct trigger;
2. wrong trigger rejection;
3. exact object association;
4. ambiguous identity;
5. client-boundary rejection;
6. healthy/recovered condition;
7. waiting condition;
8. unchanged recheck duplicate suppression;
9. changed recheck resume;
10. remediation-required condition;
11. denied/unauthorized action;
12. failed action;
13. bounded retry exhaustion;
14. human-review condition;
15. authoritative verification;
16. terminal ticket-state write/readback;
17. persisted restart/resume behavior;
18. scheduled-job cleanup;
19. active-slot release while waiting;
20. observability state.

---

## 22. Common Observability Contract

Every active playbook instance should expose at least:

- ticket/case ID;
- playbook ID/version;
- client;
- target;
- lifecycle state;
- classification;
- queue owner;
- active vs waiting;
- last meaningful change;
- next action/recheck;
- retry count;
- blocking reason;
- human action required yes/no;
- active job/correlation ID;
- last verification time.

This is the common Grafana-facing operational model.

---

## 23. New-Playbook Authoring Goal

The target authoring experience is:

1. choose the standard template;
2. fill in the manifest;
3. define expected state;
4. define evidence questions;
5. define classifications;
6. map classifications to wait/remediate/review/complete;
7. define authoritative verification;
8. define only truly playbook-specific gates;
9. run the standard acceptance suite;
10. request exact autonomy promotion for eligible branches.

A new playbook should not require bespoke implementations of ticket claiming, scheduling, retry tracking, note formatting, state persistence, handoff, or terminal readback.

BackupIQ is the initial reference implementation for this model because it exercises multi-provider evidence, offline waiting, provider cycles, asset lifecycle, remediation, retries, verification, recovered-alert closure, and human exceptions.

## Integration Coordination Note — 2026-09-29

PR #603 was reviewed for overlap with this runtime standard. Its shared-runtime changes are limited to VulScan client-disposition and client-notification behavior; this branch's runtime changes are limited to BackupIQ waiting/resume behavior. The overlapping files contain separate functional hunks and no conflicting lifecycle or authority semantics were identified.
