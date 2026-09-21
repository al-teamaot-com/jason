# INF-016 — Kyocera Fleet Services Provider Foundation

**Status:** Implemented foundation; live activation blocked pending AOT Kyocera API contract and credentials  
**Mode:** Governed read-only  
**Provider:** Kyocera Fleet Services (KFS)  
**Canonical host:** `https://api.kyods.com`

## Purpose

Provide Project Jason with a governed provider boundary for Kyocera Fleet Services
so copier/MFP identity, meter, supply, and alert data can be queried through the
Central Orchestrator without direct provider access from agents or conversations.

## Canonical capabilities

- `print.device.search` -> `kyocera_kfs.device.search`
- `print.device.read` -> `kyocera_kfs.device.get`
- `print.meter.read` -> `kyocera_kfs.meters.get`
- `print.supplies.read` -> `kyocera_kfs.supplies.get`
- `print.alert.search` -> `kyocera_kfs.alerts.list`

All capabilities are read-only, client-scoped, deterministic, audited, and fail
closed.

## Credential boundary

Logical secret: `kyocera_kfs.readonly`

OpenBao path:
`secret/data/connectors/kyocera-kfs/production/read-only`

The provider uses its own least-privilege AppRole and the existing JKD-003
short-lived runtime token pattern. KFS credentials and operation/header
configuration are never stored in source.

## Private provider contract

Kyocera publicly documents the KFS API integration capability and API host, but
the detailed dealer operation/header contract is supplied to authorized dealers.
Jason therefore does not guess provider paths or header names.

`headers_json` and `operations_json` are stored with the KFS provider secret.
Only provider-local paths on `api.kyods.com` are allowed, and only GET/POST
operations are accepted by this read-only foundation.

## Live enablement gate

KFS remains blocked unless all of the following are true:

1. AOT receives the official Kyocera dealer API credential package.
2. AOT receives the exact header and operation-path contract.
3. The contract and credentials are provisioned through the governed OpenBao
   provider-secret lifecycle.
4. Credential-safe verification succeeds.
5. A controlled read-only query validates response shape and client isolation.
6. `JASON_KFS_ENABLED=true` is explicitly set in the runtime.

Until then the provider is registered as planned/blocked/unavailable and cannot
be selected by governed capability resolution.

## Explicit exclusions

This foundation does not enable:

- remote device configuration;
- firmware updates;
- remote service actions;
- credential disclosure;
- billing writes;
- Autotask writes;
- any KFS write or destructive capability.

Those require separate governance and capability approval.
