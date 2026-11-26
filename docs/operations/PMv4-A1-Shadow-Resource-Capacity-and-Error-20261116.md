# PMv4 A1 isolated shadow resource and failure-attribution correction

**Status: source-only preproduction engineering. Not installed, not signed, not operational.**

## Facts from November 16, 2026 failed exact release

Owner signed original A1 exact release scope
`7e1f62de1a10e46db934792967f43e03e778990d2764ea42cbdde1657dc61716`
and approval `owner-mcp-319c697027a146beac98818e5305a971`.
Root staged source and native receipt, launched the isolated OpenClaw gateway,
then reported `HostGateDenied:PMV4_HOST_TRANSACTION_UNAVAILABLE`. A1
was **not accepted**. Shadow pointer returned to the original 40-zero
empty baseline. The disconnected image was observed at approximately
**511.9 MiB / 512 MiB**, **60 of 64 PIDs**, and **50% CPU** (the configured
half-core quota). Health checks timed out and a Node process asserted
`uv_thread_create` failed. Production host memory was ~25 GiB available;
the failure was local to the intentionally isolated shadow resources.

The exact one-container Docker Compose project was checked against image ID,
source and component labels, and deactivated without removing state volumes
or altering Ticket Core, MCP or freeze/hold. The original root-only audit
and native receipt remain pending reconciliation via source-only PR #2501.
**Do not reissue or reuse the original Owner approval to promote**.

## Narrow preproduction profile correction

Compared byte-for-byte to protected main source
`8c2064193d74cc41b52369681febbc0a74fa96f7`:

| Isolated shadow property | Failed profile | Proposed bounded profile |
|---|---:|---:|
| cgroup PIDs | 64 | 256 |
| memory limit | 512 MiB | 2 GiB |
| CPU limit | 0.5 core | 1.0 core |
| health command timeout | 8 seconds | 15 seconds |
| start period | 60 seconds | 120 seconds |

No other source Compose values are changed. The network remains **none**,
with no published ports, root filesystem remains read-only, UID/GID 1000,
ALL capabilities dropped, no-new-privileges, no restart policy, secret token
only in its isolated preproduction profile, and no provider credentials,
host socket or production volume mounts. Source-unit tests prove precisely
these five values changed and verify Compose dry-run JSON interpretation.
Resource sizing is a hypothesis supported by observed container saturation,
not proof of actual successful runtime health. A future governed on-host
isolated pilot must independently demonstrate healthy state and rollback
before A1 is declared operational.

## Correct masking of native release errors

Existing `tools/pmv4_host_release_guard.py::host_release_transaction`
used to wrap the entire `yield` body with `except OSError` and replace
any internal Docker/restore/file exception with
`PMV4_HOST_TRANSACTION_UNAVAILABLE`. The failure message could therefore
be a *misleading wrapper*, not an actual shared-lock acquisition failure.

The proposed source fix catches OSError only while opening or locking the
two existing native host lock inodes, and leaves errors raised by the release
body unchanged. It preserves fixed lock order, nonblocking fail-closed
behavior, nested acquisition rejection, breaker enforcement and lock
cleanup. Tests assert a synthetic ENOMEM inside the held transaction is
preserved, a genuine lock-open OSError is still reported as a host gate
failure, and unrelated host-gate denials propagate.

## Governance and sequencing

Do NOT merge this source patch or replace the root-installed Compose as a
one-off workaround. The original A1 release immutable packet is pinned
to protected main SHA 8c206419... and Compose/manifest hashes; this draft
changes the source profile, so a completely new SHA-bound A1 packet, reviewed
scope, immutable rollback, exact Owner authorization and separate production
activation will be required after the failed original root transaction is
fully reconciled. Preparation can continue independently, but **no fresh
approval should be requested until the non-mutating root preflight and
all source CI, capacity, health and rollback checks are demonstrably ready**.

C/D/E do not inherit authorization from this proposal. Production ticket
processing, freeze, hold, root watchdog and PMv3 services must remain intact.
