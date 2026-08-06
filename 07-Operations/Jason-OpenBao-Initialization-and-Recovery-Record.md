# Jason OpenBao Initialization and Recovery Record

## Purpose

This record is the canonical non-secret evidence for OpenBao initialization, seal configuration, custody, bootstrap disposition, and recovery testing.

It must never contain unseal shares, recovery keys, root tokens, bootstrap tokens, passwords, or secret values.

## Current decision

The current Jason OpenBao pilot is **BLOCKED**. It is initialized and uses manual Shamir unseal, but the custody chain and recovery evidence have not been verified.

| Field | Value | Status |
|---|---|---|
| Component | OpenBao pilot | Verified |
| Initialization status | Initialized | Verified from health response |
| Seal or recovery method | Manual Shamir unseal | Verified from configuration and local design documentation |
| Share count | 5 | Documented design; operational evidence UNVERIFIED |
| Recovery threshold | 3 | Documented design; operational evidence UNVERIFIED |
| Custody assignments | UNVERIFIED | Blocking |
| Protected custody reference | UNVERIFIED | Blocking |
| Bootstrap credential disposition | UNVERIFIED | Blocking |
| Operational owner | UNVERIFIED | Blocking |
| Escalation contact | UNVERIFIED | Blocking |
| Last successful recovery test | NOT TESTED | Blocking |
| Recovery evidence reference | MISSING | Blocking |

## Required ceremony evidence

Before this record may be marked ready, a governed ceremony must verify without recording secret values:

1. The initialized component identity, version, storage backend, and environment.
2. The approved seal or recovery mechanism.
3. The configured share count and threshold.
4. Separate custody assignments or approved protected custody references.
5. Confirmation that no recovery material remains in Git, chat, tickets, shell history, ordinary files, or unattended output.
6. The disposition of the initial bootstrap or root credential.
7. Named operational ownership and escalation responsibility.
8. A successful recovery test using the approved threshold or an approved pilot reinitialization followed by recovery verification.
9. Evidence paths, timestamps, approvals, and hashes that contain no protected values.

## Hard gate

No stateful infrastructure component may be promoted to operational readiness, used for provider credentials, or depended upon by a live capability while any required field is missing, unverified, not tested, contradictory, or stale.

## Current remediation choices

The governed operator must choose one of the following:

- recover the existing instance using verified custody material and complete a recovery test; or
- approve pilot reinitialization after confirming that no production secrets or required state will be destroyed, then perform a complete initialization and recovery ceremony.

The decision and evidence must be recorded here before dependent live execution is permitted.
