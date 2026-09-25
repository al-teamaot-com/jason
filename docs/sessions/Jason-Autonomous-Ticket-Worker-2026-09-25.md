# Jason Autonomous Ticket Worker - Production Scope

**Date:** 2026-09-25  
**Status:** Implemented; production activation is separately owner-gated.

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

Production activation is disabled by default with
`JASON_AUTONOMY_WORKER_ENABLED=false`. When explicitly enabled, the worker runs
on the runtime server's owning thread, uses a durable SQLite operational ledger,
and limits concurrent autonomous work to the configured Jason autonomy slot
limit (default two).

The ordinary shadow assessor continues to run independently so unmatched or
not-yet-autonomous tickets can still be evaluated without mutation.
