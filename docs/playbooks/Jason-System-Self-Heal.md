# Jason Playbook: System Self-Heal

```yaml
playbook:
  id: system_self_heal
  name: Jason System Self-Heal
  version: 1.1.0
  owner: AOT IT Operations
  target_type: service
  trigger:
    provider: Jason production health
    match: any already-approved Jason function is degraded, unavailable, stale, inconsistent, failing acceptance, or failing its expected operational outcome
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 2
  recheck:
    enabled: true
    cadence: 5m
    stale_after: 30m
  verification:
    authoritative_source: affected function plus independent production health evidence
    success_condition: affected function passes its normal functional acceptance check
  completion:
    terminal_disposition: restored or owner_action_required
  autonomy:
    allowed_branches:
      - start/restart an existing Jason service/container when it is not running
      - one bounded restart of jason-mcp-pilot when its functional status probe fails
      - create a deduplicated self-heal incident and invoke the autonomous SUPPORT repair lane
    approval_bound_branches:
      - authority expansion
      - new provider permission or capability
    disruptive_branches:
      - host reboot
      - host shutdown
```

## 1. Section Goal
**Goal:** Jason restores any detected non-fully-functional state in an already-approved Jason function without waiting for an owner prompt when recovery is within existing authority.

**Success means:** degradation is detected independently of process-up state; infrastructure, capability, workflow, semantic-outcome, and anomaly failures can all surface health incidents; bounded safe recovery is attempted; the affected function is verified end-to-end; source defects enter autonomous SUPPORT repair; duplicate incidents are suppressed; the owner is contacted in Teams only when Jason cannot safely continue.

## 2. Trigger
Any production health/control-plane check reports an already-approved Jason function degraded, unavailable, stale, inconsistent, or failing its accepted behavior. This includes explicit failed health metrics, failed Jason systemd units, overdue/failed operational outcome contracts, and persisted workflow verification states that exceed their expected completion window.

## 3. Scope and Boundaries
In scope: Jason runtime, MCP/control plane, autonomous worker, governed provider paths, work-state reporting, support-repair automation, release reconciliation, Teams transport, observability required for proof, persisted recheck/state mechanics, semantic outcome verification, and workflow/anomaly detection.

Out of scope: new business capability, provider bypass, secret exposure, cross-client scope expansion, constitutional change, or unapproved host reboot/shutdown.

Preserve Central Orchestrator, `direct_provider_access=false`, exact grants, provider/client isolation, audit, rollback, and existing approval rules.

## 4. Initial Identification
Identify the degraded function, authoritative failing evidence, production revision, last healthy evidence, expected outcome contract when applicable, persisted workflow state, and a stable incident fingerprint. Do not infer a provider outage from a failed local tool call alone.

## 5. Expected State
The affected function passes its established functional acceptance check and produces the expected independently verifiable operational outcome, not merely process liveness.

## 6. State Model
`healthy -> degraded -> diagnosing -> recovering -> verifying -> recovered`

Alternate states: `repair_required`, `waiting_external_dependency`, `owner_action_required`.

Persist fingerprint, evidence, attempts, recovery actions, incident/support reference, and notification marker.

## 7. Diagnostic Workflow
Check independent production health evidence, exact service/container state, failed Jason systemd units, functional MCP/status probe, provider canaries, operational outcome contracts, and relevant persisted worker state. Distinguish transport, service, runtime, provider, source-code, authority, workflow-stall, semantic-verification, and external dependency failures.

Detection layers are:
1. **Infrastructure health** — containers/services, source/image contract, timers/exporters, filesystem/runtime dependencies.
2. **Capability health** — missing/erroring capability discovery, unexpected authorization/read/write failure, provider/canary failure, failed readback.
3. **Workflow health** — stuck active/verification states, work that exceeds its expected state deadline, queue/worker state contradictions.
4. **Semantic outcome health** — an action is not healthy until the promised result is independently verified (for example, a client notification requires NotificationHistory evidence; ticket completion requires PSA readback; cleanup requires current free-space improvement and monitor reconciliation).
5. **Outcome/anomaly health** — material operational deviations such as repeated identical failures or a pipeline producing implausibly no progress should generate a reviewable health signal rather than silently appearing healthy.

## 8. Decision Gates
Recovery must remain within existing approved authority; must target an exact Jason component; must not broaden provider/client scope; must not expose secrets; and must not require host reboot/shutdown.

## 9. Remediation
Allowed bounded recovery includes starting a stopped existing Jason container/service and one bounded restart of `jason-mcp-pilot` when its functional status surface fails. Unresolved defects are persisted to the self-heal incident spool and immediately wake the native autonomous SUPPORT repair worker.

## 10. Retry Policy
Maximum two bounded recovery attempts for one unchanged failure fingerprint. Do not repeat identical recovery indefinitely.

## 11. Periodic Rechecks
Run every five minutes. Re-evaluate the complete functional state after any recovery action. Evaluate registered operational outcome contracts and selected persisted verification phases against explicit deadlines. Unchanged healthy checks create no operational noise.

## 12. Aging / Stale Condition
A degraded state surviving the bounded retry budget becomes `repair_required`; if the SUPPORT repair lane cannot restore it, it becomes `owner_action_required`.

## 13. Dependency Handling
Persist external dependencies explicitly. Continue unrelated healthy Jason work. Never fabricate configuration, credentials, identities, or provider state.

## 14. Documentation Requirements
Persist the incident fingerprint, failing evidence, health layer, affected workflow/object where applicable, recovery attempts, support item, verification outcome, and escalation reason. Do not record secrets.

## 15. Failure Handling
A failed health read, restart, SUPPORT repair, deployment, workflow verification, semantic outcome verification, or independent readback is evidence. It must advance the persisted state rather than silently ending the cycle. Unknown/missing required verification is degraded, not healthy.

## 16. Escalation Criteria
Teams the owner only for broader authority/new permission, disruptive action, unresolved identity/evidence ambiguity, constitutional/governance change, unsafe provider bypass, unsatisfied external dependency, or exhausted bounded recovery/repair.

## 17. Verification
Re-run the exact affected functional check after remediation and, where applicable, independently verify the promised operational outcome. Process running is insufficient when the original failure was functional or semantic.

## 18. Completion Criteria
Complete only after the affected function passes authoritative verification and the self-heal state records recovery. Source fixes additionally require production deployment/acceptance.

## 19. Final Resolution Note
Record degraded function, fingerprint, root cause when known, actions attempted, support/PR/release references, authoritative verification, and final disposition.

## 20. Required Capabilities
Host health reads, Docker service state/start/restart for exact Jason containers, Jason user-systemd failure reads, production health metrics, operational outcome-contract spool, persisted autonomy-work health reads, self-heal persisted spool, support-repair wake/integration, GitHub support repair lane, governed Teams owner notification, and production verification.

## 21. Acceptance Test
Prove: a synthetic recoverable MCP functional failure is detected, bounded recovery occurs, exact function verification succeeds, no owner notification is sent; prove a failed Jason systemd unit is detected; prove an overdue generic outcome contract is detected; prove a stalled VulScan client-notification verification state becomes a health incident; prove a verified outcome is not flagged; then prove an unrecoverable synthetic condition enters SUPPORT repair and, after bounded exhaustion, produces exactly one governed Teams escalation containing evidence, attempts, blocker, and required owner action.

## 22. Section Goal Closure
Close only after the watchdog is production-installed, its five-minute timer is active, the bounded MCP status response is production-proven through the exposed tool path, infrastructure/capability/workflow/semantic detection is production-proven, client-notification semantic verification is monitored for staleness, auto-generated self-heal incidents are accepted by the native SUPPORT repair worker, and governed Teams escalation is verified.

## 23. Autonomous Execution Eligibility and Owner Review
Owner instruction dated 2026-09-30 authorizes bounded self-remediation of detected non-fully-functional Jason states within existing authority. This does not grant new provider authority, constitutional authority, secret access, client-scope expansion, or host reboot/shutdown authority.
