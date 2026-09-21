# Kyocera Fleet Services connector

This package implements Jason's governed Kyocera Fleet Services (KFS) provider
using the KFS External Integration API User Guide v6.2.

## Runtime behavior

KFS uses two distinct authentication layers:

1. Dealer API gateway authorization in the HTTP `Authorization: Basic ...` header.
2. A KFS Manager-or-higher username/password in the JSON body of `/KFS/Login`.

Jason logs in at the start of a governed provider call, keeps the returned KFS
cookie in memory only, uses it for the requested read operations, and discards
the session with the short-lived connector instance.

Canonical host: `https://api.kyods.com`
API version: `6`

## Logical secret

`kyocera_kfs.readonly`

Runtime fields:

- `api_url`
- `request_from`
- `request_to`
- `authorization`
- `kfs_username`
- `kfs_password`

The gateway Authorization value and KFS Manager login are separate credentials.

## Implemented provider operations

- `/KFS/Login` - establish the KFS session
- `/KFS/GroupList` - discover accessible group roots
- `/KFS/DeviceList` - search devices across group trees
- `/KFS/Device` - device identity, counters, and consumables
- `/KFS/DeviceLogList` - group alert/event history
- `/KFS/DeviceLog` - device alert/event history

Jason capabilities:

- `kyocera_kfs.device.search`
- `kyocera_kfs.device.get`
- `kyocera_kfs.meters.get`
- `kyocera_kfs.supplies.get`
- `kyocera_kfs.alerts.list`

These map to the canonical `print.*` capabilities already registered by the
Central Orchestrator.

## Governance

This activation remains read-only and fail-closed. The KFS write endpoint
`/KFS/ChangeStatus` is deliberately not exposed by this connector.

The runtime remains gated by `JASON_KFS_ENABLED`; production enablement should
occur only after credential-safe live validation succeeds.

## Current live blocker

The Kyocera-issued gateway Authorization credential is accepted by the API
gateway. The currently vaulted gateway ID/password pair is the same pair encoded
inside that Authorization value, but KFS returns body status 401 when that pair
is used as the `/KFS/Login` Manager login.

KFS v6.2 documents that the login body requires a KFS Manager-or-higher user.
A previously working AOT integration used a dedicated KFS Manager account named
`apiuser`. Live activation therefore remains blocked on a valid KFS Manager
login only; the Kyocera-issued API credentials must not be reset or changed.
