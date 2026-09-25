# Jason Autonomous Ticket Worker - Production Scope

**Date:** 2026-09-25  
**Status:** Production active for the separately promoted EDR/AV health-only branch.

## Purpose

Jason may continuously review the Autotask **Help Desk I**, **Help Desk II**, and
**Monitoring Alert** queues and perform bounded autonomous ticket work when an
exact production playbook has separate durable owner approval.

This is not unrestricted autonomy. Human governance remains authoritative.

## First autonomous resolver

The first production resolver is the health-only branch of
**Jason - Datto EDR/AV Diagnose & Repair v1.3.0**.

Eligible tickets must:

1. match the health-only `Antivirus status` trigger;
2. not be a `Security Threat detected` ticket;
3. have an existing active Autotask configuration item;
4. have an exact CI `referenceNumber` that matches a live governed Datto device;
5. have a CI hostname that exactly matches the Datto hostname;
6. have the endpoint online at admission;
7. have the exact playbook version and capabilities covered by a durable owner promotion.

For eligible work Jason may:

1. move the ticket to the **Jason** queue;
2. set status to **In Progress** and work type to **Remote Support**;
3. run the standing-safe EDR/AV health component;
4. if `Status=Healthy` is not proven, run exactly one separately standing-safe
   `Datto EDR Force Reinstall and Upgrade` attempt;
5. rerun the authoritative health component;
6. create an internal Autotask note;
7. mark the ticket **Complete** only after authoritative `Status=Healthy` is
   observed and the ticket-update connector verifies provider readback.

## Hard stops

The worker does not autonomously:

- process threat-triggered EDR/AV tickets;
- reboot or schedule a reboot;
- run generic PowerShell;
- perform a clean EDR/AV uninstall;
- continue after stale/unknown Datto job state;
- redispatch a job when a read/poll fails;
- work an endpoint that is offline;
- work a ticket with missing/ambiguous/inactive device identity;
- communicate with the client.

Those paths remain technician-review or per-run approval paths.

## Authority

The workload principal remains `jason-autonomy-worker`. Production execution
requires exact JKD-001 grants plus a separate durable playbook promotion for only:

- `automation.component.execute`
- `service.ticket.note.create`
- `service.ticket.update`

Read grants are exact and limited to the queue/device/job evidence required by
the worker. The runtime cannot create or broaden these grants itself.

Owner-only MCP controls were added to report, approve, and revoke the production
ticket-worker authority.

## Runtime

Production source defaults remain fail-closed, but the approved production deployment now has
`JASON_AUTONOMY_WORKER_ENABLED=true`. The worker runs
on the runtime server's owning thread, uses a durable SQLite operational ledger,
and limits concurrent autonomous work to the configured Jason autonomy slot
limit (default two).

The ordinary shadow assessor continues to run independently so unmatched or
not-yet-autonomous tickets can still be evaluated without mutation.

## Production completion record

Production activation was completed on 2026-09-25. The durable operational promotion is `pbauto_d754251d9ae140fe9a3fa11b090eaf49` for `datto_edr_av@1.3.0`. The autonomous workload uses Autotask Resource `29682930` and the standing-safe Datto component registry.

The first production reconciliation exposed a provider-evidence normalization defect on `T20260921.0015` / `gai-lt2820`: the governed Datto path supplied provider-native `uid` while the worker expected canonical `resource_id`. No remediation was executed. PR #349 added safe normalization for `resource_id`, `uid`, or `deviceUid` while retaining exact UID and hostname matching. It was deployed at revision `aaa536cef3e10edac8a1cc41595caee19be570c6`.

After deployment, `jason-runtime` was healthy with both the autonomous ticket worker and Datto autonomous standing-safe execution enabled. The false blocked state for ticket ID `140792` was removed after the defect fix. Because `gai-lt2820` was offline, reevaluation correctly left no persistent active/blocked work row and performed no provider mutation.

Operational procedures and the expansion checklist are maintained in `docs/operations/JASON_AUTONOMOUS_TICKET_WORKER.md`.
