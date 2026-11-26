# PMv4 Stage E — distinguish live Ticket Core from root acceptance

Status: source-only. No production changes, retirements, approval or authority.

Following the successful November 18 Stage C canonical independent-worker
handoff, the previous Stage E attestor still emitted
STAGE_C_INDEPENDENT_WORKER_NOT_ACCEPTED unconditionally. This false negative
masked important remaining retirement requirements.

The Stage E read-only gate now inspects exactly three Docker facts:
the existing runtime's external-worker hosting flag (without printing any
other environment variables), the separate Ticket Core worker's running
status, and that worker's healthy status. Live production returns three PASS
observations, with recent zero-duplicate provider-backed ticket scans.

Root-only Stage C acceptance receipts and exact protected desired-state
readbacks are not accessible to the read-only user. The attestor now reports
STAGE_C_ROOT_ACCEPTANCE_RECEIPT_NOT_READBACK when the independent worker is
live rather than making a false claim that no worker exists or that root
acceptance was independently verified. It still blocks any PMv3 retirement
unless root attestation, replacement controller parity, Stage D acceptance,
and exact Owner retirement proof are independently verified. Unknown or
unhealthy worker status continues to fail closed.

No new authority, Docker mutation, systemd mutation, provider action,
runbook write or protected policy change. Tests validate live, embedded,
unhealthy and forbidden Docker-inspect formats.
