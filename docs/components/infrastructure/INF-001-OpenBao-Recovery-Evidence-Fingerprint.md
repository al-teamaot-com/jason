# INF-001 OpenBao Recovery Evidence Fingerprint

## Purpose

This control binds the protected OpenBao initialization artifact to non-secret operational evidence without storing or displaying any unseal share, root token, bootstrap token, password, or secret value.

The fingerprint supplements the canonical initialization and recovery record. It does not replace custody distribution, ownership, escalation, or periodic recovery testing.

## Evidence collected

The governed collector records only:

- SHA-256 of the protected initialization JSON;
- file size, ownership identifiers, and restrictive mode;
- configured share count and threshold;
- whether an initial root token remains present, expressed only as a boolean;
- OpenBao initialization, seal, standby, version, and available cluster metadata;
- host and UTC collection time;
- an explicit assertion that protected values were not exposed.

The evidence never records the unseal shares or credential values.

## Command

Configuration-only validation:

```bash
sudo .venv-test/bin/python tools/openbao_recovery_fingerprint.py \
  --output /home/al/Jason-Evidence/OpenBao/recovery-fingerprint-check.json \
  --check-only
```

Governed evidence collection:

```bash
sudo .venv-test/bin/python tools/openbao_recovery_fingerprint.py \
  --output /home/al/Jason-Evidence/OpenBao/openbao-recovery-fingerprint-<UTC>.json
```

The output path must not already exist. Evidence is created with mode `0600`.

## Readiness rule

A recovery fingerprint is necessary but not sufficient for readiness. The stateful recovery gate must still verify:

- custody assignments or approved protected custody references;
- bootstrap credential disposition;
- operational owner and escalation contact;
- a successful recovery test;
- evidence references and review status.

Any fingerprint mismatch, unexpected permission broadening, share-design contradiction, or inability to reach the health endpoint blocks recovery readiness pending governed review.
