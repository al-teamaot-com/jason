# Jason Playbook: VulScan Multi-Device Ticket Split

```yaml
playbook:
  id: vulscan_multi_device_split
  name: Jason - VulScan Multi-Device Ticket Split
  version: 1.0.0
  owner: AOT IT Operations
  target_type: ticket
  trigger:
    provider: autotask
    match: VulScan missing-patch ticket containing two or more affected nodes
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: next autonomy scan after retryable failure
    stale_after: 24h
  verification:
    authoritative_source: Autotask + Datto RMM
    success_condition: one verified child ticket per verified device
  completion:
    terminal_disposition: Complete
  autonomy:
    allowed_branches:
      - parse_multi_device_alert
      - resolve_exact_targets
      - split_into_verified_child_tickets
      - document_lineage
      - complete_source_after_verified_split
    approval_bound_branches: []
    disruptive_branches: []
```

## 1. Section Goal

**Goal:** Safely convert one VulScan source ticket that names multiple affected devices into one independent, verified child ticket per device so the normal one-ticket/one-device VulScan workflow can operate without weakening identity governance.

**Success means:**
- every affected node resolves to exactly one same-company active Autotask CI and exact Datto RMM endpoint;
- one child ticket is created per verified device;
- every child has exactly one CI and durable source-ticket lineage;
- retries do not create duplicate child tickets;
- the source is completed only after every requested child is verified by provider readback.

## 2. Trigger

Apply only when:
- the ticket matches the VulScan missing-patch trigger; and
- the ticket description contains an `Affected Nodes:` section with two or more independently named devices.

A single-device VulScan ticket stays on the existing `vulscan_missing_patch` playbook.

## 3. Scope and Boundaries

### In Scope
- parse affected device names from the VulScan alert;
- resolve exact same-company Autotask CI and Datto UID/hostname for every node;
- use the shared Jason Ticket Split Runtime Contract;
- create one child ticket per verified target;
- preserve source-ticket lineage;
- complete the source only after all children are verified.

### Out of Scope
- guessing among ambiguous device matches;
- altering vulnerability findings;
- patch approval;
- patch installation;
- reboot;
- client communication;
- provider writes outside the governed ticket-create/update/note capabilities.

Preserve Central Orchestrator authority, exact owner/playbook grants, client isolation, audit, and `direct_provider_access=false`.

## 4. Initial Identification

1. Read the exact source ticket.
2. Confirm the source company.
3. Parse every affected node from the VulScan description.
4. Require at least two unique node names.
5. For each node, search active same-company Autotask configurations by exact RMM hostname/name.
6. Require exactly one CI with a non-empty Datto/DRMM resource ID.
7. Read the Datto endpoint by that exact resource ID.
8. Require endpoint UID readback equality and exact hostname equality.
9. Resolve every target before creating any child.
10. If any target is ambiguous or unresolved, fail closed without completing the source.

## 5. Expected State

Healthy split state is:
- one child ticket per source affected node;
- each child belongs to the source company;
- each child is in queue Jason, status New;
- each child has exactly one configuration item;
- each child description contains the source ticket number and deterministic split marker;
- the durable split ledger records source ticket + target UID -> child ticket ID;
- source ticket contains a note listing the verified child ticket IDs;
- source ticket is Complete only after all children have verified readback.

## 6. State Model

`detected -> multi_device_identified -> targets_resolving -> targets_verified -> source_claimed -> children_creating -> children_verified -> lineage_documented -> source_completed`

Failure branches:
- `targets_resolving -> identification_blocked`
- `children_creating -> retryable_failure`
- `children_verified -> lineage_documentation_failed`
- `source_completed` is terminal only after every child is verified.

Persisted child mappings survive retries and restarts.

## 7. Diagnostic Workflow

### A. Parse source alert
Extract node names only from the bounded VulScan `Affected Nodes:` section.

### B. Resolve target identity
For each node:
- exact same-company active CI lookup;
- exact CI `referenceNumber` as Datto UID;
- exact endpoint read by UID;
- exact endpoint UID and hostname readback.

### C. Build child definition
Each child copies bounded source context:
- company;
- priority;
- issue type;
- subissue type;
- ticket type;
- relevant finding text.

Child-specific values:
- title includes the target hostname;
- configuration item is the target CI only;
- queue = Jason;
- status = New;
- description includes target hostname, Datto UID, source ticket number, and split marker.

## 8. Decision Gates

Before any child create:
- source is a qualifying multi-device VulScan alert;
- at least two unique targets;
- all targets resolve exactly;
- exact `vulscan_multi_device_split@1.0.0` durable promotion is active;
- that promotion includes `service.ticket.create`, `service.ticket.note.create`, and `service.ticket.update`;
- shared split runtime is available.

Before source completion:
- requested target count equals verified child count;
- every child has durable provider readback;
- source lineage note has been attempted successfully;
- no unresolved target remains.

## 9. Remediation

This playbook does not remediate endpoints. Its only modifying actions are PSA ticket lifecycle operations:
- claim source;
- create child tickets;
- add source lineage note;
- complete source after verified split.

Child tickets are then processed independently by the existing VulScan playbook.

## 10. Retry and Recheck Rules

- verified children are persisted and reused;
- a retry creates only missing children;
- source/target mapping cannot be rebound to a different child ID;
- provider create/readback failure stops the split attempt;
- source remains open until all children are verified;
- duplicate target names in one source fail closed.

## 11. Dependencies

- shared Jason Ticket Split Runtime Contract;
- governed `service.ticket.create`;
- Autotask configuration search/read;
- Datto endpoint read;
- Autotask ticket update/note create;
- durable playbook promotion store;
- durable split ledger.

## 12. Documentation

Source note must include:
- count of child tickets;
- each target hostname;
- each verified child ticket ID;
- statement that each child has one verified CI;
- statement that no endpoint remediation occurred during splitting.

Each child description must include:
- source ticket number;
- target hostname;
- Datto UID;
- deterministic split marker;
- original relevant VulScan finding.

## 13. Failure and Escalation Handling

Fail closed when:
- any target cannot resolve exactly;
- exact split promotion is absent;
- ticket-create capability is unavailable;
- provider readback fails;
- persisted split mapping conflicts.

Retryable provider failures may be retried. Identity ambiguity requires Human Review rather than guessing.

## 14. Verification

For every child:
- provider returns a durable ticket ID;
- post-create readback verifies company and title;
- durable split ledger records the child only after verification.

For the source:
- completion update requires provider readback of status.

## 15. Completion

Complete the source only when:
- every parsed target has a verified child;
- all child mappings are durable;
- lineage note is written;
- source Complete status is read back successfully.

## 16. Required Capabilities

Exact autonomous write scope:
- `service.ticket.create`
- `service.ticket.note.create`
- `service.ticket.update`

Read dependencies:
- `service.configuration.search`
- `endpoint.device.read`

No endpoint execution capability is authorized by this playbook.

## 17. Acceptance Test

Controlled acceptance:
- source ticket T20260929.0033, company 208, KB5129195, four affected nodes.

Prove:
1. four node names are parsed;
2. each resolves to exactly one active same-company CI and exact Datto endpoint;
3. source is claimed into Jason/In Progress;
4. four child tickets are created in Jason/New;
5. each child has exactly one correct CI;
6. each child contains source lineage;
7. all four creates have provider readback;
8. repeat invocation creates zero duplicate children;
9. source note lists all verified children;
10. source completes only after all four children exist.

Secondary controlled case:
- T20260930.0041 may be used later to validate another five-node source, but it should not be replayed simultaneously if doing so would create duplicate remediation work for the same KB/device set.

## 18. Required Capabilities and Authority Review

The shared splitter grants no authority. This playbook's exact durable promotion supplies the bounded ticket-create/update/note authority.

The existing `vulscan_missing_patch@1.0.0` and `@1.1.0` approvals are unchanged and do not inherit ticket-create authority.

## 19. Final Resolution Note

The source split note should state:
- original VulScan finding / KB;
- affected-node count;
- verified child IDs and target hostnames;
- that each child carries one CI;
- that no patch remediation was performed on the source ticket.

## 20. Observability

Record:
- split attempts;
- created vs reused child counts;
- target-resolution failures;
- provider readback failures;
- source completion verification;
- duplicate suppression events.

## 21. Acceptance Criteria

- generic ticket split primitive tests pass;
- VulScan integration tests pass;
- full runtime-service suite passes;
- strict documentation build passes;
- exact split playbook promotion is durable;
- one controlled real source proves child creation and retry idempotency;
- source/child lineage is visible in Autotask.

## 22. Section Goal Closure

Close only after:
- source code and docs merge;
- production deployment is verified;
- exact `vulscan_multi_device_split@1.0.0` promotion is active;
- controlled live acceptance succeeds;
- issue #814 records the production proof and any remaining macOS AV work separately.
