# Jason Waiting Device Access — Production Acceptance — 2026-09-27

## Goal

Make endpoint availability a first-class automatic Jason queue lifecycle state so offline device tickets do not remain misleadingly **In Progress**, do not consume one of the two active-work slots, and automatically resume when access returns.

## Accepted behavior

For a ticket already owned by Jason with exact active Autotask CI -> DRMM UID identity and exact durable playbook authority for `service.ticket.update`:

1. read current endpoint availability through the governed DRMM path;
2. if offline, set Autotask status **Waiting Device Access**;
3. do not create/persist active operational work for that offline ticket;
4. keep the ticket in the Jason queue and include **Waiting Device Access** in owned-status reconciliation;
5. do not repeat the status write while the ticket remains waiting;
6. when current endpoint evidence becomes online, use the normal claim transition to restore **In Progress** and resume the matched playbook.

Tickets outside the Jason queue are not claimed or status-mutated merely because a pre-claim availability check finds them offline. Unmatched or unpromoted work remains fail-closed. **Waiting Device Access** is not **Human Review** and does not transfer responsibility to Help Desk I.

## Production reconciliation

Before deployment, the live Jason queue contained nine **In Progress** tickets. Exact CI -> DRMM device reads showed eight endpoints offline and one endpoint online. The eight offline tickets were moved through the governed ticket-update capability to **Waiting Device Access** with provider write/readback verification. `T20260923.0075` / VZ-HYPER-V remained **In Progress** because its exact endpoint was online.

Post-reconciliation live queue state:

- **Waiting Device Access:** 8 tickets;
- **In Progress:** 1 ticket;
- online in-progress ticket: `T20260923.0075` / VZ-HYPER-V.

## Source and CI

PR #420, **Automate Waiting Device Access lifecycle**, merged as source revision `5e57a34ac2018bad032e3b4467c58f814023699f`. Protected validation passed:

- Validate Jason;
- SEC-007 Security Regressions;
- Datto EDR AV Playbook;
- Validate Jason Teams Gateway;
- Validate Conversation Experience Foundation.

Focused local autonomy/runtime regression coverage also passed. The new tests prove:

- one-time offline transition to **Waiting Device Access**;
- no active operational-work row/slot while offline;
- no duplicate update when already waiting;
- automatic return to **In Progress** and normal playbook resume when online;
- BackupIQ and VulScan now wait for endpoint availability before active diagnostics.

## Production deployment

The merged revision was built as an immutable runtime candidate and deployed through the rollback-protected production helper. The lower-level deployment succeeded and the runtime became healthy at `5e57a34...`, but the outer refresh wrapper immediately performed a second verification, returned a false failure, and restored the canonical runtime image aliases to the old image. Independent readback proved the running runtime itself was healthy on the new revision with zero restarts.

The canonical aliases were reconciled to the already-running proven image without restarting Jason. The prior runtime remained preserved as `jason-runtime:rollback-current`.

MCP was then built from the same source revision and deployed through its rollback-protected helper. The MCP governance postcheck passed, including Central Orchestrator governance and `direct_provider_access=false`. The prior MCP rollback image/container was preserved.

Finally, the host-service reconciliation installed `/opt/jason/releases/5e57a34ac2018bad032e3b4467c58f814023699f`, moved `/opt/jason/current` to that immutable release, and reconciled the Jason host exporters/maintenance units.

## Final independent readback

- `/opt/jason/current` -> `/opt/jason/releases/5e57a34ac2018bad032e3b4467c58f814023699f`;
- `jason-runtime` source revision `5e57a34...`, health `healthy`, restart count `0`;
- `jason-mcp-pilot` source revision `5e57a34...`, state `running`, restart policy `unless-stopped`;
- Jason client posture, playbook, production health, resolution memory, security control, status, usage attribution, and usage exporters all active;
- delegation-maintenance and OpenClaw-authority-health timers active;
- no failed systemd units;
- live Autotask queue readback remained 8 **Waiting Device Access** / 1 **In Progress**.

## Result

**PRODUCTION ACCEPTED / WORKSTREAM CLOSED.**

Automatic device-access status management is now part of Jason's production autonomous ticket lifecycle and is documented as a governed lifecycle behavior, not an ad hoc manual cleanup procedure.
