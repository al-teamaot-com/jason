# INF-016 - Kyocera Fleet Services Provider Foundation

**Status:** Implemented; first Jason live collection successful; production activation pending durable Manager-secret promotion and runtime/timer cutover
**Mode:** Governed read-only  
**Provider:** Kyocera Fleet Services (KFS)  
**Canonical host:** `https://api.kyods.com`  
**API contract:** KFS External Integration API User Guide v6.2

## Purpose

Provide Project Jason with a governed provider boundary for Kyocera Fleet
Services so copier/MFP identity, meter, supply, and alert data can be queried
through the Central Orchestrator without direct provider access from agents.

## Canonical capabilities

- `print.device.search` -> `kyocera_kfs.device.search`
- `print.device.read` -> `kyocera_kfs.device.get`
- `print.meter.read` -> `kyocera_kfs.meters.get`
- `print.supplies.read` -> `kyocera_kfs.supplies.get`
- `print.alert.search` -> `kyocera_kfs.alerts.list`

All capabilities are read-only, deterministic, audited, and fail closed.
The first production activation is restricted by the connector to AOT-internal
organization-wide reads (`organization_id=aot`, `client_id=None`). Per-client
KFS access remains denied until explicit KFS serial-to-Autotask mapping and a
canonical Jason client boundary are present. Production selection remains gated
by `JASON_KFS_ENABLED`.

## Authentication boundary

KFS requires two separate authentication layers.

1. The Kyocera-issued dealer API Authorization credential is sent in the HTTP
   `Authorization: Basic ...` header.
2. `/KFS/Login` requires a KFS Manager-or-higher username and password in the
   request body.

The login response supplies KFS cookie state. Jason keeps that cookie only in
memory for the duration of the provider call and does not persist it.

Logical secret: `kyocera_kfs.readonly`

OpenBao path:
`secret/data/connectors/kyocera-kfs/production/read-only`

Runtime fields:

- `api_url`
- `request_from`
- `request_to`
- `authorization`
- `kfs_username`
- `kfs_password`

## Implemented API operations

- `POST /KFS/Login`
- `POST /KFS/GroupList`
- `POST /KFS/DeviceList`
- `POST /KFS/Device`
- `POST /KFS/DeviceLogList`
- `POST /KFS/DeviceLog`

Fleet device search discovers KFS root groups through `GroupList` and calls
`DeviceList` with group target scope 1, which includes the specified group and
child groups. Results are deduplicated by KFS device ID.

Meters and consumables use the documented `Device` endpoint. Alerts use
`DeviceLog` for a known device or `DeviceLogList` for a group tree.

## Historical evidence plane

Jason also maintains an append-oriented PostgreSQL history store populated by
the deterministic KFS collector running every 6 hours. The restored Claw history and all new
Jason collections use the same schema, preserving continuity across the
migration.

The historical store includes run metadata, raw provider responses, groups,
devices, meter readings, consumable readings, device status readings, device
logs, and per-run device deltas. PostgreSQL remains local-only on
`127.0.0.1:5432`; provider credentials are not stored in the database.

The collector is source-controlled under `infrastructure/kfs-collector/` and
runs at 00:00, 06:00, 12:00, and 18:00 America/New_York after production cutover. Live provider reads
remain authoritative for current-state questions; PostgreSQL history is the
longitudinal evidence source for prior-state, trend, delta, billing-validation,
and correlation workflows.

## Explicit write exclusion

KFS documents `POST /KFS/ChangeStatus`, but it is not exposed by this
read-only activation. Any future KFS write capability requires separate Jason
governance, mutation authority, verification, and acceptance testing.

## Validation

The KFS provider-specific GitHub Actions validation and the full Jason validation
suite both pass with the documented session implementation.

Credential-safe live testing established the root cause and successful path:

- the Kyocera API gateway accepts the existing dealer Authorization credential;
- the previously vaulted Manager fields had been populated with that same
  gateway identity, which KFS rejects for `/KFS/Login`;
- the working AOT/OpenClaw Manager identity is the separate account `apiuser`;
- a verified Claw-to-Jason handoff of that Manager pair was used for one
  controlled validation run without changing the durable OpenBao secret;
- Jason `/KFS/Login` returned status 200 and a session cookie;
- the full 2026-09-22 collection completed with status `ok`, 0 errors,
  235 groups, 432 current devices, 7,274 meter readings, 1,509 consumable
  readings, 549 device-log readings, and 472 raw KFS responses;
- the restored PostgreSQL history was successfully appended by the live run.

The connector now also fails closed if the Manager username/password exactly
matches the dealer Basic credential pair, preventing recurrence of this
misconfiguration.

## Live activation gate

The API/session blocker is resolved. Production KFS remains disabled until the
remaining promotion steps are completed:

1. Promote the verified separate Manager pair into the six-field OpenBao secret
   without changing the dealer Authorization credential.
2. Rebuild/deploy the Jason runtime with the KFS AppRole mounts present.
3. Deliberately set `JASON_KFS_ENABLED=true`.
4. Validate governed device search/read, meter, supplies, and alert capabilities.
5. Install and enable the midnight America/New_York collector timer and verify
   its first scheduled run.
6. Only after those checks succeed, disable the legacy Claw KFS job.

The Kyocera-issued dealer API gateway credential must not be reset or replaced
as part of this promotion.
