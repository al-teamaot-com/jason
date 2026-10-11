# Root-protected release-control bridge (readback foundation)

The production watchdog owns the authoritative circuit-breaker and drift state. The unprivileged release manager must not be given direct write authority to those files merely to bypass a failed deployment gate.

`tools/release_control_bridge_worker.py` is an isolated, root-only **readback publisher**. It validates the ownership, file type, mode and schema of both authoritative files and publishes copies with operator-only read permissions. This helper performs no circuit-breaker mutations and is not installed or invoked in production by this change.

**NOT PRODUCTION READY:** Before activation, a separate guarded privileged operation must handle circuit-breaker transitions and bind requests to a verified candidate, active release lock, authoritative manifest and exact owner authorization. Snapshots alone cannot authorize promotion; freshness, atomic paired snapshots and policy consistency must be verified. Never interpret the presence of a snapshot as an approval, never bypass fail-closed behavior, and never use a temporary ownership change as the deployment fix.
