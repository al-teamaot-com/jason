# Jason Kyocera KFS data source

This directory owns the durable Kyocera Fleet Services (KFS) collection path
used by Project Jason.

KFS is treated as a governed read-only data source with two complementary
planes:

1. Live provider reads through the canonical Jason `print.*` capabilities.
2. Append-oriented PostgreSQL history populated by the nightly KFS collector.

The history database preserves device, meter, supply, status, and device-log
observations so Jason can support trend and prior-state workflows without
discarding the current KFS API view.

## Governance

- KFS access is read-only.
- `/KFS/ChangeStatus` is not exposed.
- The dealer API credential and KFS Manager login are separate identities.
- KFS Manager credentials must not equal the Basic dealer credential pair.
- Production capability selection remains gated by `JASON_KFS_ENABLED`.
- The PostgreSQL service is bound only to `127.0.0.1:5432`.
- Claw must not be retired until Jason live reads, history collection, and the
  midnight timer are all verified.

## Components

- `kfs_collector.py` - deterministic read-only KFS collector and PostgreSQL writer.
- `container_run_kfs.py` - resolves the governed OpenBao KFS secret and launches the collector.
- `run_kfs_collector_container.sh` - short-lived container launcher.
- `compose.yaml` - local-only PostgreSQL definition.

- `systemd/jason-kfs-collector.service` - oneshot collector service.
- `systemd/jason-kfs-collector.timer` - midnight America/New_York schedule.
- `install.sh` - installs the collector and timer without enabling the timer by default.

## Authentication

Logical OpenBao secret:

`kyocera_kfs.readonly`

Path:

`secret/data/connectors/kyocera-kfs/production/read-only`

Required fields:

- `api_url`
- `request_from`
- `request_to`
- `authorization`
- `kfs_username`
- `kfs_password`

The `authorization` field is the Kyocera-issued dealer API Basic credential.
The `kfs_username` and `kfs_password` fields are the separate KFS
Manager-or-higher login used in the JSON body of `/KFS/Login`.

The dedicated runtime AppRole is stored under:

`/opt/jason/bootstrap/secrets/openbao/kyocera-kfs-read-approle/`

## First successful Jason live collection

Validated on 2026-09-22:

- Run ID: `29c778b6-c86c-431b-b5bc-e014740194b6`
- Status: `ok`
- Errors: `0`
- Groups: `235`
- Current devices: `432`
- Raw KFS responses: `472`
- Meter readings written: `7,274`
- Consumable readings written: `1,509`
- Device status readings written: `432`
- Device log readings written: `549`
- Device run deltas written: `432`

The restored PostgreSQL history plus this live run produced:

- `kfs_runs=59`
- `kfs_raw_responses=22563`
- `kfs_devices=439`
- `kfs_meter_readings=357513`
- `kfs_consumable_readings=75809`
- `kfs_device_status_readings=21602`
- `kfs_device_log_readings=24343`
- `kfs_device_run_deltas=21194`

The historical device table intentionally retains devices no longer present in
the current 432-device live fleet.

## Promotion sequence

1. Merge the KFS data-source changes and rebuild `jason-runtime:local`.
2. Update only the KFS Manager fields in OpenBao using
   `tools/kfs_manager_handoff_update.py`; preserve the dealer credential.
3. Run `provider_secret.py verify kyocera_kfs`.
4. Install this collector with `./install.sh`; leave the timer disabled.
5. Run one controlled collector invocation and require `status=ok` and
   `errors=0`.
6. Recreate the Jason runtime with the KFS AppRole mounts and
   `JASON_KFS_ENABLED=true`.
7. Validate governed reads for device search, device read, meters, supplies,
   and alerts.
8. Enable the midnight timer:
   `systemctl --user enable --now jason-kfs-collector.timer`
9. Confirm the timer is scheduled and the next run succeeds.
10. Only then disable the legacy Claw KFS job.

## Failure behavior

A failed KFS login stops the collection immediately. The collector does not
retry authentication, does not call mutation endpoints, and records a failed
run rather than partially presenting the collection as healthy.

If the governed live provider fails, keep `JASON_KFS_ENABLED=false` and do
not retire Claw. If the nightly collector fails after live provider promotion,
retain the last known-good PostgreSQL history and investigate before changing
KFS credentials.

## Evidence

Collector artifacts are written under:

`/home/al/jason-evidence/kfs-runs/<UTC-run-id>/`

Each run contains redacted request/response evidence, logs, a manifest,
`results.json`, and `summary.json`. Secret values must never be persisted
in those artifacts.
