# PMv4 Stage C — reviewed external worker state and credential projection

**Status:** SOURCE-ONLY, no installed external worker and no permission grant. The original production embedded ticket worker, A1 shadow, freeze/hold and all existing provider credentials remain unchanged.

## Why this is required

With the ticket-only early-return composition merged in #2512, offline construction still opens 11 SQLite databases. Some are canonical authority/provider audit/approval records, not worker-owned. Mounting `/var/lib/jason/openclaw` into the independent Ticket Core would expose unrelated PM work and violate compartmentalization; binding isolated SQLite database files without their WAL/SHM/lock directory would be unsafe.

The exact structural profile in `tools/pmv4_ticket_core_exact_projection.py` is a **positive test target**, not an approval or installed configuration. It requires only:

1. `/var/lib/jason/ticket-core` RW for the canonical ticket work, promotions, targeted wake and adjacent ticket-split (and optionally client-question) ledgers.
2. Existing `/var/lib/jason/authority` RW for the same canonical identity/authority and Microsoft boundary records used by production. No new authority store or grants.
3. A separately created `/var/lib/jason/governed-ticket-shared` RW for the exact canonical shared Autotask/Microsoft identity bindings, governed execution ledger, orchestration events, reflection and resolution memory. The current live copies must be migrated consistently with all producers quiesced under an approved release, not just copied while other services write.

It also pins **20 individual read-only OpenBao AppRole file mounts** (not their contents) corresponding to verified existing live production Autotask, Datto RMM/EDR, Backup.net, Microsoft Graph, OpenAI and SES projections. All 20 paths were independently compared to the live runtime's read-only mount list on November 17; all matched. These path names do not grant access. No generalized secrets directory, Docker socket, host filesystem, or wildcard mount is allowed. The root release must independently verify actual paths, file metadata, AppRole scope and outbound egress before it can use this profile.

A source-only worker settings change separately forces the ticket child to disable HTTP conversation handling, Teams/Owner approval scheduling, mobile release worker, autonomous review and unrelated support/DRMM/Windows Time loops. It retains the active Ticket Core, provider capability flags and hosted-analysis settings. It does not change any HTTP or auxiliary process profile.

## Remaining signed release obligations

Before production, a governed root transaction needs to stop new work admission, drain and record in-flight claims, maintain one child owner lock, take a consistent SQLite+WAL snapshot of all required stores, preserve a complete original state backup, move both producers and consumer paths to one shared canonical record set, and atomically enable only one independent worker. Exact provider roles and egress must be bound to the new candidate and signed scope; both owner and rollback evidence are required. Provider-backed acceptance requires two real distinct scheduled Autotask scans without duplicate work, notes, notifications or lost approvals. Rollback must retain any new authoritative writes, never silently replace them with a stale pre-cutover copy.

The pure source profile returns `root_owner_release_verified=false` and `external_worker_ready=false`; its pass does **not** demonstrate production readiness. Current protected Ticket Core continues processing during this work. The exact release installer and root-signed Owner decision remain separate and unissued.
