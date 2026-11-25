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

## Stop misleading recovery cycles on exhausted handoffs

The same production investigation found owner-approved development records
already at `internal_retry_exhausted` with durable
`recovery_handoff_intake.status = awaiting_governed_repair` and existing
`SUPPORT-DEV-...` issues. Examples include DEV-1196 (#1586) and DEV-1444
(#1450). The native development worker deliberately prohibits another
unverified retry; the supervisor incorrectly counted their old HTTP transport
errors as immediate `recoverable_transport` progress.

The supervisor now classifies an exhausted record with a verified existing
handoff as `governed_repair_handoff`, with the original SUPPORT-DEV ID
preserved for follow-up. Exhausted records lacking a valid handoff remain
`needs_triage` rather than gaining retry authority. Neither category can
trigger the PMV3 controller's automatic recoverable-pass loop by itself.
Unknown triage is not a verified executable recovery action.

This is scheduling and evidence accuracy, **not completion** of the
governed repair handoff. Do not retry failed reasoning requests without the
worker's independent same-schema transport proof, source/test evidence and
applicable authorizations. Existing release locks and provider/owner policy
remain controlling.

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

## November 25 native successor reconciliation

The installed system-manager pipeline contract at 0e8008f0a5577b4fd30804bbefe0db2134341778 passed native admission and six of seven work stages. The real scheduled cycle beginning at 14:35 EST failed TODO intake on the original open #1459/#1500 collision. The existing exact approved failed-acceptance transaction restored the engineering pause at 14:43:06 EST; production drift remained clear, the breaker closed, and the conflicting identities and earlier approvals were preserved.

PR #2296 is reconciled with that protected-main baseline. It groups the entire valid issue inventory before quarantine, so identical early duplicates cannot disappear from a later divergent group's evidence. Unknown and saturated inventories remain fail-closed. Intake suppresses duplicate creation and reports the full quarantine; the existing release bridge retains its independent historical binding hold. No existing issue is closed, edited, rebound or granted new authority, and the approved parallel development worker and its claim policy are unchanged.

The existing exact native PipelineSuccessor transaction now supports this reviewed predecessor/profile. It proves the prior immutable receipt and failed-acceptance pause, pins the three replacement worker files and the complete previous artifact inventory, retains the existing systemd sandbox, configuration, freeze, hold and protected services, and publishes a new receipt only through the existing independently authenticated Owner scope. The source candidate may not broaden native targets or bypass the root release transaction. Rollback retains the original pause and restores exactly the prior files/receipt. The previous activation failure and approval stay immutable.

Use the native installer with --todo-conflict-successor from the exact current protected-main source and mandatory CI attestation. No installation is inferred from the merged PR. Native scheduled acceptance requires two distinct normal completed cycles, all seven stages successful, fresh TODO quarantine and supervisor hold, successful watchdog, fresh dependency admission/conflict enforcement, unchanged protected peers, drift PASS and breaker CLOSED. Each cycle is recorded in a root-private immutable receipt; any intervening failed stage prevents a false terminal acceptance. The work item remains quarantined pending independently verified reconciliation of its two scopes. This repair does not itself prove independent concurrent development or completion of the wider backlog.

The live isolated inventory contained more than 150 supervisor dispositions. Authority-hold rows are now prioritized in the bounded report so the exact quarantined TODO remains visible; full counts and the disposition fingerprint still cover the entire inventory.
