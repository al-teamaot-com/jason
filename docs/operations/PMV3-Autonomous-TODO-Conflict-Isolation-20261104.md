# PMV3: Isolate conflicting TODO identities without stalling unrelated engineering

## Incident and authority boundary

On 2026-11-04, the installed five-minute engineering pipeline repeatedly failed
`todo_intake` because **two different open GitHub issues** declared the same
`- TODO item: TODO-OPS-013` identity:

- #1459 — managed distributed development workers.
- #1500 — approved device provisioning and service offload.

Both contain materially different titles and bodies. Neither may be selected,
closed, merged, reinterpreted or treated as new approval by the intake worker.
The existing owner-approved development worker and Release Manager retain their
independent admission and production gates. Do not create a second engineering
queue or invent broader authority to resolve a conflicting source identity.

## Correction in the existing intake / supervisor

- The full 5,000-item GitHub issue inventory remains required. An unreadable,
  malformed or saturated inventory still fails closed.
- Strict source-identity callers continue raising on divergent issues. The
  scheduled intake passes an explicit conflict ledger, retains the oldest
  issue **only for duplicate suppression**, and quarantines the TODO identity.
  This choice is **not** approval of either issue's implementation scope.
- The durable intake state records every conflicting GitHub issue number/URL,
  the blocked exact TODO identity, `new_work_authorized: false`, and the
  next gate: `reconcile_exact_issue_scope_and_owner_authority`.
- Each additional open conflicting issue consumes conservative TODO issue
  capacity. Unrelated approved items may still be admitted when all normal
  support-first and issue-capacity gates permit it.
- A new conflicting issue or exhausted capacity discovered on the mandatory
  immediate pre-create GitHub re-read prevents creating a new issue.
- The supervisor surfaces a quarantined identity under the existing
  `human_authority` category. It cannot characterize such a conflict as a
  healthy empty queue or turn the conflict into a recoverable provider write.

## Acceptance / monitoring

Source tests cover divergent and identical duplicate handling, more than two
conflicting issues, no new authority, full-inventory saturation, unrelated
TODO admission, race-condition re-read and supervisor evidence. Relevant
engineering-worker, controller and release bridge regressions must also pass.

A read-only, isolated-spool GitHub provider replay on 2026-11-04 confirmed
`TODO-OPS-013` was quarantined with issue numbers `[1459, 1500]`.
The replay did not create an issue, modify production state, or deploy.

Following a separately authorized deployment, verify two consecutive complete
five-minute engineering cycles: intake succeeds with the conflict recorded;
unrelated development, integration and release stages continue under their
own controls; the conflict does not authorize a fresh TODO-OPS-013 issue; and
the controller's measured forward progress is reported independently of
service exit code. Report counts of actual resolved commitments, not merely
succeeded worker processes.

## Unresolved work and release controls

The identity conflict still requires reconciling issue authority/source
between #1459 and #1500. This repair deliberately does not make that decision.

The pipeline also has other stranded development items (transport, source
context, validation and protected production-release dependencies). Quarantine
does **not** resolve their individual blockers or prove autonomous production
acceptance. The existing worker's verified-transport readmission, dependencies,
retry budgets and exact-SHA release approvals must remain intact.

Source integration and any production promotion are controlled by Project
Jason's protected release manager. A passing PR, a scheduled timer or a
conversational `proceed` is not exact-SHA production authorization.
