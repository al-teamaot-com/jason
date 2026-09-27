# Resolution Memory First Verified Case Pre-Acceptance — 2026-09-27

**Status:** Review-only candidate validated; production ingestion intentionally deferred  
**Roadmap:** TODO-OPS-001  
**Candidate:** AVMAC-1096 / T20260924.0043 Idle Log Off repair

## Purpose

Prepare the first production Resolution Memory case using authoritative, already-verified operational evidence without writing anything to the live Resolution Memory database while the Owner is out of office.

## Authoritative identity and boundary evidence

Governed Autotask reads confirmed:

- ticket: T20260924.0043
- Autotask ticket ID: 141066
- company ID: 1179
- company: AVMAC llc
- configuration item ID: 1583
- DRMM alert UID: 9d34f135-8393-4e7f-b2a8-064a1e98eb07
- ticket status: Complete
- ticket completed: 2026-09-25T16:49:38.763Z
- client UDF: Enforce Idle Log Off = True

Jason's current scoped-context implementation uses the string Autotask company ID as the client_id. Therefore the reviewed Resolution Memory boundary is:

- organization_id: aot
- client_id: 1179

The namespaced company value used in an ingestion unit-test fixture was not treated as production identity.

## Verified operational outcome

The canonical Idle Log Off playbook records the controlled production acceptance:

- legacy 08202024 tooling returned Invalid MyFileDestination;
- Compliant=False was not treated as sufficient proof by itself;
- Set Idle Log Off AOT Ver 02042026-1 ran exactly once under owner approval using built-in defaults;
- setter output reported successful staging and scheduled-task creation;
- independent read-only verification showed AOT_IdleLogOff Ready, SYSTEM, Highest, running C:\Temp\MyIdleLogOff\MyIdleLogOff.exe with arguments 240 60 and exit code 0;
- no immediate forced logoff or reboot occurred;
- the stale DRMM alert was resolved through the governed alert-resolution path with verified readback;
- Autotask completed the ticket and recorded the final internal resolution note;
- standing-safe promotion of the setter remained rejected because it intentionally affects future user sessions.

## Review-only candidate

The candidate JSON is:

docs/sessions/resolution-memory/AVMAC-1096-Idle-Log-Off-Resolution-Candidate-2026-09-27.json

It preserves reusable incident characteristics in the signature while keeping unique ticket/device/alert identifiers in source provenance.

The setter remains:

- approval_required = true
- disruptive = true
- grants_authority = false

Historical evidence therefore cannot independently authorize the same action later.

## Disposable-store validation

The exact production ingestion tool was run against a temporary SQLite database only.

Result:

- candidate status: verified
- same-client read for client 1179: PASS
- cross-client read using client 311: correctly returned no case
- same-client similarity search: 1 matching case
- top match: AT-T20260924.0043-IDLE-LOGOFF
- Resolution Memory result grants_authority: false

Historical step aggregation returned:

- idle_log_off.alert.classify -> insufficient_history
- idle_log_off.mechanism.verify -> insufficient_history
- aot.idle_log_off.setter.02042026-1 -> insufficient_history, approval required, disruptive

That is the desired first-case behavior. One successful historical case does not become accepted operational truth.

## Production state

No production Resolution Memory record was created during this review.

## Remaining controlled acceptance

When the Owner is available, or if a separately approved safe ingestion window is designated:

1. re-read the exact ticket/company boundary;
2. confirm no material evidence has changed;
3. run the reviewed candidate through tools/ingest_resolution_case.py against the production Resolution Memory database;
4. require status=verified and client_id=1179;
5. perform governed operations.resolution.read for the exact case from client 1179;
6. prove the same case is not readable under another client scope;
7. run a same-client operations.resolution.search using the reviewed Idle Log Off signature;
8. confirm grants_authority=false throughout;
9. record aggregate Resolution Memory metrics/readback;
10. leave TODO-OPS-001 open until a later materially similar AVMAC case proves real reuse rather than merely first-case storage.

This package grants no new write, provider, client, disruption, or autonomous authority.
