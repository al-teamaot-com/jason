# INF-016 - Kyocera Fleet Services Provider Foundation

**Status:** Implemented and validated in code; live activation blocked on KFS Manager login  
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

All capabilities are read-only, client-scoped, deterministic, audited, and
fail closed. Production selection remains gated by `JASON_KFS_ENABLED`.

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

## Explicit write exclusion

KFS documents `POST /KFS/ChangeStatus`, but it is not exposed by this
read-only activation. Any future KFS write capability requires separate Jason
governance, mutation authority, verification, and acceptance testing.

## Validation

The KFS provider-specific GitHub Actions validation and the full Jason validation
suite both pass with the documented session implementation.

Credential-safe live testing also established:

- the Kyocera API gateway accepts the existing Authorization credential;
- the vaulted gateway ID/password pair exactly matches the pair encoded in that
  Authorization value;
- using that gateway pair as the `/KFS/Login` body credentials returns KFS
  status 401.

The v6.2 guide requires a KFS Manager-or-higher user for the login body. A prior
working AOT/OpenClaw integration used a dedicated KFS Manager account named
`apiuser`.

## Live activation gate

Production KFS remains disabled until all of the following are true:

1. A valid KFS Manager-or-higher integration login is available.
2. The six-field runtime secret is present behind the dedicated KFS AppRole.
3. Credential-safe `/KFS/Login` returns KFS status 200.
4. Controlled `GroupList` and `DeviceList` reads validate response shape.
5. A controlled meter, supplies, and alert read succeeds.
6. `JASON_KFS_ENABLED=true` is deliberately enabled.

The Kyocera-issued API gateway credential must not be reset or changed as part
of resolving the KFS Manager-login blocker.
