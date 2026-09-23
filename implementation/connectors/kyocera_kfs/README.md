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

The first production scope is AOT-internal organization-wide access only. The
connector requires `organization_id=aot` and `client_id=None`; any client-scoped
request is rejected before secret resolution or provider contact. Per-client
KFS access requires an explicit serial-to-Autotask mapping and canonical Jason
client boundary before it can be exposed.

The runtime remains gated by `JASON_KFS_ENABLED`; production enablement occurs
only after credential-safe live validation and deliberate promotion.

The connector rejects a secret when the Manager username/password exactly
matches the dealer Basic credential pair. KFS requires those identities to be
separate.

## Live validation status

The original 401 blocker was traced to the Manager fields being populated with
the dealer gateway identity. The working AOT Manager account is the separate
`apiuser` identity.

On 2026-09-22, a verified Manager credential handoff was injected only for one
controlled Jason validation run while the existing dealer Authorization and
request-routing values remained unchanged. `/KFS/Login` returned status 200 and
a session cookie, and the full collection completed with 0 errors across 235
groups and 432 current devices.

The durable OpenBao secret still requires promotion of the verified Manager
fields before `JASON_KFS_ENABLED` is turned on. The Kyocera-issued dealer API
credential must remain unchanged.
