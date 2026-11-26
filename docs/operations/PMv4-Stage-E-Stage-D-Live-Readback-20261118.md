# PMv4 Stage E: independent Stage D live readback

**November 18, 2026 — source-only. No production mutation or retirement.**

Stage D was accepted by its exact local Owner-controlled release
6dc78887b636dce5066871a3076bfe75bcd84ad3.
The live host showed jason-runbook-management-read.service active and enabled,
with a Unix socket mode 0600 owned by the existing Jason service UID 1000.
Read-only status and snapshot both reported healthy, registry generation 0,
zero active JSON playbooks, no provider calls, no configuration mutations,
and no execution authority. Ticket Core remains external and healthy and
MCP remains running. The protected production breaker remains closed.

The existing Stage E read-only retirement attestor still hardcoded
STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED irrespective of service
state. This source-only patch makes that observation precise. The attestor
reads only systemctl is-active/is-enabled for the one approved Stage D unit,
then sends only the fixed status request over the local AF_UNIX socket. It
requires a non-symlink directory owned by UID 1000 mode 0700, a real socket
owned by UID 1000 mode 0600, a peer UID 1000, a bounded response, and an exact
read-only status response (healthy, nonnegative integer registry generation
and active_count, false provider_calls/execution_authority/configuration_mutations).
No network connection, file write, privileged token, provider call, or
systemd mutation is possible through the readback code.

An independently healthy live service is NOT a substitute for the root-only
Stage D acceptance receipt. The gate therefore changes from
STAGE_D_INDEPENDENT_RUNBOOK_MANAGEMENT_NOT_ACCEPTED to
STAGE_D_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK when live verification passes.
An absent, unhealthy, insecure or unreachable service remains a blocker.
The Stage C root receipt, root-protected live desired-state policy, PMv4
replacement-controller parity and exact authenticated Owner retirement release
all remain independent unresolved requirements. No PMv3 timer is disabled.

Tests cover live, absent and stopped units; forbidden systemctl writes;
same-UID local Unix socket; exact status operation; insecure socket mode;
and a response claiming provider authority. All fail closed.
