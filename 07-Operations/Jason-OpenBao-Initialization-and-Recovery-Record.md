# Jason OpenBao Initialization and Recovery Record

## Purpose

This record is the canonical non-secret evidence for OpenBao initialization, seal configuration, custody, bootstrap disposition, and recovery testing.

It must never contain unseal shares, recovery keys, root tokens, bootstrap tokens, passwords, API credentials, or secret values.

## Current decision

The current Jason OpenBao pilot is initialized, unsealed, and operational. A successful 3-of-5 unseal was performed using protected initialization material without displaying protected values. The record remains **BLOCKED** only where human governance decisions or restore evidence are still missing.

| Field | Value | Status |
|---|---|---|
| Component | OpenBao pilot | Verified |
| Initialization status | Initialized | Verified from health response |
| Version | `2.6.1` | Verified |
| Cluster ID | `62dc5d61-5b8a-5939-6ed3-e913d45d189c` | Verified |
| Cluster name | `vault-cluster-b84f0e4e` | Verified |
| Storage backend | Integrated Raft | Verified |
| Seal or recovery method | Manual Shamir unseal | Verified |
| Share count | 5 | Verified from protected initialization structure |
| Recovery threshold | 3 | Verified from protected initialization structure |
| Protected initialization reference | `/opt/jason/bootstrap/secrets/openbao/init.json` | Verified; `root:root`, mode `0600` |
| Protected artifact SHA-256 | `877c7ff2688282444a1f232f3e12bec633dad09349513c48431da9aaf7a7d6c6` | Verified fingerprint only |
| Custody assignments | Protected single-host pilot custody; named custodians not recorded | Blocking |
| Protected custody reference | Existing protected file retained for pilot recovery; governance approval not recorded | Blocking |
| Bootstrap credential disposition | Bootstrap token revoked and temporary bootstrap files removed | Verified |
| Runtime credential disposition | Dedicated orphan token installed at `/etc/jason/openbao.token` | Verified |
| Operational owner | UNVERIFIED | Blocking |
| Escalation contact | UNVERIFIED | Blocking |
| Last successful recovery test | 2026-08-06; three shares accepted and service became unsealed | Verified |
| Recovery evidence reference | `/home/al/Jason-Evidence/OpenBao/openbao-recovery-fingerprint-20260806T113030Z.json` | Verified |
| Bootstrap retirement evidence | `/home/al/Jason-Evidence/Secret-Provider/openbao-bootstrap-retirement-20260806T120329Z.json` | Verified |
| Last successful Raft restore test | UNVERIFIED | Blocking |

## Verified ceremony summary

The governed recovery investigation established the following without exposing protected values:

1. The protected initialization file exists and is mode `0600`, owned by `root:root`.
2. Its structure contains five base64 and five hexadecimal unseal-share representations with a threshold of three.
3. Three shares were supplied directly from the protected file to OpenBao.
4. OpenBao accepted each share and transitioned from sealed to unsealed after the third share.
5. No share, root token, bootstrap token, password, or secret value was printed.
6. A non-secret fingerprint evidence artifact recorded the artifact hash, size, ownership, permissions, share design, cluster identity, OpenBao version, and seal state.
7. The commissioning bootstrap credential was later revoked and removed.
8. The replacement runtime token is an orphan token, so future bootstrap retirement cannot revoke the runtime identity through token hierarchy.

## Remaining governance requirements

The following decisions must be completed before the recovery record may be declared fully ready:

- name the operational owner;
- name the escalation contact;
- explicitly approve or replace the current single-host protected custody model;
- document named custody assignments if split custody is required;
- complete a controlled Raft snapshot restore test and reference its evidence;
- confirm the automated backup service is healthy after repair.

## Hard gate

No live capability may treat recovery as fully ready while a required field is missing, contradictory, stale, or marked as requiring governance approval. The successful unseal proves that the current protected material can recover the seal state; it does not by itself approve custody, ownership, escalation, backup, or restore controls.

## Evidence handling rule

Evidence may contain paths, timestamps, versions, hashes, file modes, ownership identifiers, cluster identifiers, boolean status, and redacted outcomes. Evidence must never contain protected values or enough material to reconstruct them.
