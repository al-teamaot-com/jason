# Jason OpenBao Initialization and Recovery Record

## Purpose

This record is the canonical non-secret evidence for OpenBao initialization, seal configuration, custody, bootstrap disposition, and recovery testing.

It must never contain unseal shares, recovery keys, root tokens, bootstrap tokens, passwords, API credentials, or secret values.

## Current decision

The current Jason OpenBao pilot is initialized, unsealed, and operational. The single-host pilot now has an approved root-only automatic recovery control for host/OpenBao restart recovery. OpenBao remains Shamir-sealed, 3-of-5, but the already-retained protected initialization artifact may be used locally by `jason-boot-recovery.service` to restore the approved pilot after restart without printing or persisting the shares elsewhere.

This is an explicit **single-host pilot exception**, not a claim of split-custody protection against host-root compromise. Future multi-host/production deployment still requires an approved hardware/KMS auto-unseal design or true off-host custody.

| Field | Value | Status |
|---|---|---|
| Component | OpenBao pilot | Verified |
| Initialization status | Initialized | Verified from health response |
| Version | `2.6.1` | Verified |
| Cluster ID | `62dc5d61-5b8a-5939-6ed3-e913d45d189c` | Verified |
| Cluster name | `vault-cluster-b84f0e4e` | Verified |
| Storage backend | Integrated Raft | Verified |
| Seal or recovery method | Shamir 3-of-5 with approved root-only local automatic unseal for the single-host pilot | Verified / Owner-approved 2026-09-24 |
| Share count | 5 | Verified from protected initialization structure |
| Recovery threshold | 3 | Verified from protected initialization structure |
| Protected initialization reference | `/opt/jason/bootstrap/secrets/openbao/init.json` | Verified; `root:root`, mode `0600` |
| Protected artifact SHA-256 | `877c7ff2688282444a1f232f3e12bec633dad09349513c48431da9aaf7a7d6c6` | Re-verified 2026-09-24 |
| Custody model | Protected single-host pilot custody retained on the Jason host for automated recovery | Owner-approved pilot exception |
| Bootstrap credential disposition | Bootstrap token revoked and temporary bootstrap files removed | Verified |
| Production provider runtime identity | Provider-specific AppRoles with short-lived tokens; IT Glue/Autotask host artifacts are restaged into protected `/run` paths after reboot | Verified |
| Boot recovery controller | `/usr/local/sbin/jason-boot-recovery` | Installed 2026-09-24 |
| Boot recovery service | `jason-boot-recovery.service` | Enabled; successful non-disruptive production run 2026-09-24 |
| Recovery timer | `jason-boot-recovery.timer` | Enabled and active; two-minute idempotent recovery check |
| Operational owner | AOT Infrastructure Owner | Approved governance role |
| Escalation contact | AOT Security Escalation | Approved governance role |
| Last successful OpenBao recovery | 2026-09-24; protected 3-of-5 shares accepted and OpenBao transitioned sealed -> unsealed without share disclosure | Verified |
| Recovery evidence reference | `docs/sessions/Jason-Boot-Recovery-Production-Acceptance-2026-09-24.md` | Verified |
| Historical recovery fingerprint | `/home/al/Jason-Evidence/OpenBao/openbao-recovery-fingerprint-20260806T113030Z.json` | Verified |
| Bootstrap retirement evidence | `/home/al/Jason-Evidence/Secret-Provider/openbao-bootstrap-retirement-20260806T120329Z.json` | Verified |
| Last successful Raft restore test | 2026-08-06; isolated governed restore matched the live source contract | Verified |
| Full host reboot acceptance after boot-recovery deployment | Not performed on 2026-09-24 because reboot is disruptive and requires explicit approval | Pending explicit disruptive test |

## Verified recovery summary

The governed recovery history now establishes the following without exposing protected values:

1. The protected initialization file exists, is mode `0600`, is owned by `root:root`, and its SHA-256 matched the previously recorded protected-artifact fingerprint on 2026-09-24.
2. Its structure contains five Base64 and five hexadecimal unseal-share representations with a threshold of three.
3. On 2026-09-24, after a power outage left OpenBao sealed, three protected Base64 shares were submitted directly from the protected file to the local OpenBao unseal API without displaying them.
4. OpenBao accepted the three shares and transitioned to `sealed=false`.
5. The ephemeral IT Glue and Autotask AppRole staging was restored under `/run/jason-runtime-credentials/openbao` with runtime UID/GID `1000:1000`, mode `0400`, and nonzero files.
6. `jason-runtime` recovered healthy and `jason-mcp-pilot` recovered with HTTP 200; MCP restart policy is now `unless-stopped`.
7. The installed boot-recovery service completed with `JASON_BOOT_RECOVERY=PASS`, the timer is active, and a secret-pattern check of the service journal passed.
8. The commissioning bootstrap credential remains revoked and removed; production providers continue to use provider-specific AppRoles rather than a shared persistent provider token.
9. A full host reboot acceptance test was intentionally not performed because reboot is user-disruptive and requires separate explicit approval.

## Remaining production-hardening work

The current single-host pilot recovery control is accepted for the pilot. Before treating this design as a multi-host/production-grade recovery architecture:

- replace host-local Shamir recovery material with an approved hardware/KMS auto-unseal design or true off-host split custody;
- perform a controlled full-host reboot acceptance when separately approved;
- continue normal backup/restore verification cadence and record new evidence as it occurs.

## Hard gate

The boot-recovery control may restore only the already-approved single-host pilot runtime shape. It grants no new provider, client, mutation, approval, or business authority. Any missing/invalid protected-artifact metadata, incomplete credential staging, sealed OpenBao state, unhealthy runtime, or failed MCP health check must fail closed.

## Evidence handling rule

Evidence may contain paths, timestamps, versions, hashes, file modes, ownership identifiers, cluster identifiers, boolean status, and redacted outcomes. Evidence must never contain protected values or enough material to reconstruct them.
