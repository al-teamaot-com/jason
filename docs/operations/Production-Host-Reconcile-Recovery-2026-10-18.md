# P0 host reconciliation acceptance repair — 2026-10-18

Related P0 issues: #1078, #1437 (REOPENED), #1055 (REOPENED), #1101.
Code change: source-only, no production permissions, no new release authorization.

## Verified incident

The Owner explicitly approved one exact bootstrap revision
`b1ea8751af208a76e84580b5f465f7936937e1e5` (not high-risk Teams
activation). Canonical Release Manager independently passed required GitHub
checks, immutable runtime/MCP image preproduction, rollback readiness,
exact Owner grant and fresh pre-mutation CCC. A **separate, honest chat-derived**
CCC material review for this SHA passed; the expected runtime-source
`NOT_PROVEN` mismatch was admitted solely in documented candidate-transition
mode. No fake Teams receipt or CCC policy waiver was used.

At 2026-10-18 12:21 UTC, candidate runtime/MCP deployed at exact SHA.
Root host reconciliation failed `system_service_activation` because the
`jason-resolution-memory-exporter.service` listener on port 9470 was
reported with an empty kernel PID attribution `sockets=[('0.0.0.0:9470', ())]`
despite a valid systemd MainPID. The guard immediately classified that one
ambiguous observation as `owned by different/unknown process`. There is no
independent proof it was a foreign listener. A later read found the expected
systemd MainPID as the socket owner. Treat a **transient PID attribution race**
as a hypothesis supported by evidence, not a fully proven process identity.

The controller attempted rollback to the recorded LKG
`ad11c311251254d38da2c1295aadd292daed20ef`, but the root rollback script
failed its 180-second `jason-openclaw-authority-health.service` start limit
(`rc=124`). Journal evidence shows prior successful snapshots taking roughly
163, 173, and 197 seconds. The root service subsequently exited.

The release record is **state=failed, rollback_verified=false**. Root circuit
breaker is **OPEN**. Independent read-only inspection found the original
runtime (healthy), MCP, host symlink, installed controller and timer aligned;
`capture_production_manifest` was complete, with zero failed system units and
subsequent desired-state drift PASS. These observations are NOT a substitute
for the failed root rollback acceptance and must not be used to silently
clear the breaker or mark deployment complete.

## Narrow repair in this PR

1. The existing port guard is unchanged in its source/port allowlists and
   process/systemd ownership requirements. Any **known foreign PID** (including
   mixed actual+unknown listener records) still fails immediately. Only a
   socket whose PID is momentarily unreported may be reobserved within the
   existing maximum 30-second bounded check. The port is counted as owned
   **only** when *all* observed listener PID sets equal the service MainPID;
   an unattributed listener that remains unattributed at the deadline FAILS.
   No process is killed, restarted, or adopted by this helper.
2. The mandatory full JKD-001 authority-health service start timeout is
   raised **only for that unit** from 180 to 240 seconds, based on observed
   healthy executions exceeding 180 seconds. The root worker still has a
   separately enforced **360-second transaction timeout**, and the Release
   Manager still imposes **420 seconds** on host request waiting. Other
   maintenance-service 120-second limits remain unchanged. A timed-out or
   nonzero health unit remains a hard reconcile failure.
3. The exporter PID attribution guard itself is explicitly categorized as
   **protected production-control-core source**, enforced in the release
   policy allowlist and risk classifier, with exact-SHA Owner-gate tests. A
   future change to only the guard cannot silently qualify as a normal
   release and bypass the constitutional core owner review.
4. Regression covers unattributed-to-owned PID convergence, persistent
   unknown, immediate foreign/mixed-PID denial, original process isolation,
   known host-source ordering and timeout ceilings. Broad Release Manager,
   host and CCC unit tests must remain green before merge.

## Explicit limitations / acceptance

This change is source only. It has NOT been deployed and MUST NOT be described
as an accepted production reliability fix. The prior `b1ea8751...` release
is **FAILED** and must not be silently retried or re-approved by reusing the
prior exact grant. The new source requires protected GitHub review and a NEW
exact-SHA Owner authorization (plus fresh CCC material review) through the
existing governed Release Manager and isolated preproduction.

A complete future acceptance requires: actual exporter-port-owner proof for
all 10 managed services; mandatory health snapshot PASS under bounded
latency; successful root host reconciliation on both normal promotion and
controlled benign rollback; runtime/MCP/host/controller and immutable image
alignment; post-deployment CCC PASS; fresh drift PASS; a complete new LKG
manifest and no failed units. Root breaker revalidation must be governed and
independently justified; do not clear it on a passing source test alone.
High-risk Teams owner-reviewed policy and Universal Teams Approver remain OFF
until their separate real-card provenance/security acceptance.
