# Jason Playbook - Endpoint Availability Verification

## 1. Section Goal

Jason must not treat a DRMM offline flag as conclusive proof that an endpoint is powered off. If a device remains offline longer than the configured threshold, Jason should automatically attempt additional read-only verification from a suitable online managed endpoint at the same client/site when one is available. If no peer is available, the workflow remains pending with a persisted recheck instead of relying on technician memory.

## 2. Trigger

Apply whenever a playbook, ticket, alert, or diagnostic workflow encounters a managed endpoint that DRMM reports offline. Default peer-verification threshold is 2 hours since Last Seen; default post-threshold recheck is 1 hour. Calling playbooks may override both.

## 3. Scope and Boundaries

In scope: DRMM state, Last Seen, hostname, last-known IP, same-client/site peer selection, hostname resolution, ping by hostname/IP, persisted recheck state, and ticket evidence. Out of scope: reboot, service restart, network/firewall changes, Wake-on-LAN, disruptive remediation, or cross-client probing. Central Orchestrator authority, approvals, audit, client isolation, and direct_provider_access=false remain unchanged.

## 4. Initial Identification

Identify endpoint, client, site, DRMM device ID, hostname, last-known IP, DRMM state, Last Seen, and triggering ticket/alert. If client/site identity is uncertain, use identification_blocked and escalate rather than probing another network.

## 5. Expected State

Healthy means the intended managed endpoint is online/current in DRMM or independent same-site evidence explains why DRMM alone is misleading.

## 6. State Model

Persist: online, recently_offline, peer_verification_due, peer_unavailable, reachable_outside_drmm, offline_likely, inconclusive, identification_blocked, or escalated. Persist observed time, Last Seen, offline age, peer used, probe results, next recheck time, and interpretation.

## 7. Diagnostic Workflow

1. Read DRMM online state and Last Seen.
2. If online, return online.
3. If offline for less than threshold, return recently_offline and persist recheck for Last Seen + threshold.
4. If Last Seen is missing, treat peer verification as due rather than waiting indefinitely.
5. After threshold, find a suitable online managed peer in the same authorized client/site.
6. If none exists, return peer_unavailable and persist another recheck.
7. If a peer exists, resolve target hostname, ping hostname, and ping last-known IP when available using an approved read-only capability.
8. If either ping succeeds while DRMM reports offline, return reachable_outside_drmm and route toward DRMM agent/service/path diagnostics.
9. If attempted pings fail, return offline_likely but do not claim power-off is proven; persist another recheck.
10. Partial/contradictory probes return inconclusive and recheck.

## 8. Decision Gates

Require exact endpoint identity, same-client authorization, same-site confidence, an online peer, and an approved read-only probe. Never choose a cross-client peer merely to complete the check.

## 9. Remediation

Not applicable. This is an evidence/availability gate. Authority classification is read-only/non-destructive.

## 10. Retry Policy

One bounded probe set per recheck cycle. No rapid ping loops. Additional attempts occur only through persisted periodic rechecks.

## 11. Periodic Rechecks

Before threshold: recheck at Last Seen + threshold. After threshold with no peer or failed/inconclusive probe: default recheck in 1 hour. Suppress duplicate scheduled rechecks for the same endpoint/workflow generation. Stop on online, closed workflow, retired asset, invalid identity, escalation, or completion.

Deferred work is workflow state, not a technician reminder.

## 12. Aging / Stale Condition

No universal terminal age is imposed here because servers, desktops, laptops, and special-purpose devices differ. Calling playbooks define stale/escalation age and should consider retirement, replacement, rename/reimage, duplicate DRMM objects, stale CIs, or site connectivity.

## 13. Dependency Handling

If Last Seen, site mapping, peer discovery, peer probing, or durable scheduling is unavailable, record the missing dependency and preserve the intended next check. Never fabricate site relationships or silently declare the endpoint offline.

## 14. Documentation Requirements

When a ticket exists, record DRMM state/Last Seen, offline age, threshold decision, peer selected, DNS result, hostname/IP ping results, interpretation, and next recheck or diagnostic path. Suggested title: Jason - Endpoint Availability - Recheck.

## 15. Failure Handling

Record failed DRMM reads, missing Last Seen/IP, no eligible peer, DNS failure, probe execution failure, timeout, and contradictory results. Provider or ping failure is not an offline assertion.

## 16. Escalation Criteria

Escalate when identity/client/site boundaries are uncertain, required read capability remains unavailable past the calling playbook tolerance, evidence stays contradictory past aging limits, or next diagnosis requires unauthorized modifying/disruptive action.

## 17. Verification

Satisfied when DRMM returns online, or same-site peer evidence proves the endpoint is reachable outside DRMM and the workflow transitions to agent diagnostics. Failed ping is supporting evidence only.

## 18. Completion Criteria

This common playbook completes a cycle when it returns deterministic state plus any required next recheck/diagnostic path. It does not close the parent ticket.

## 19. Final Resolution Note

Owned by the calling playbook. Include availability evidence when it affected diagnosis or timing.

## 20. Required Capabilities

DRMM managed-device read including Last Seen; client/site association; same-site peer discovery; approved read-only peer network probe by hostname/IP; persisted playbook state; durable scheduled recheck execution; Autotask internal note when a ticket exists; audit/event recording.

## 21. Acceptance Test

Demonstrate: recent offline defers to threshold; threshold-exceeded requests peer verification; no peer produces peer_unavailable plus recheck; successful peer ping produces reachable_outside_drmm; failed ping produces offline_likely not confirmed_offline; unknown Last Seen does not wait forever; resume fields persist; cross-client peer is rejected; duplicate rechecks are suppressed.

## 22. Section Goal Closure

The deterministic assessment module and unit tests implement the state/evidence rules. Production closure additionally requires a governed same-site peer-probe capability and a durable scheduled-recheck service. The current JKD-009 event store explicitly persists/audits events but does not provide scheduled retries, so this Section Goal remains open until those dependencies are wired and the end-to-end acceptance test passes.
