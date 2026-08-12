# OpenClaw Ed25519 Key Rotation Host Proof — 2026-08-09

## Outcome

The overlap-first OpenClaw signing-key rotation completed successfully on the Jason host.

## Proven state

- Pre-cutover overlap contained two active trusted keys: `openclaw-gateway-1` and `openclaw-gateway-2`.
- Both keys were cryptographically accepted as `svc-openclaw-gateway` before cutover.
- Key #2 completed the full governed synthetic path through OpenClaw ingress, JKD-001 authority, governance, and the Central Orchestrator.
- The governed request completed with orchestration status `succeeded`.
- Replay of the governed request was rejected with `replay_detected`.
- No provider API was contacted and no provider credential was used.
- Only after replacement continuity was proven, Jason revoked the public trust record for `openclaw-gateway-1`.
- Post-revocation proof rejected key #1 as an unregistered signing key and continued to accept key #2.
- Final trust registry contained one active key (`openclaw-gateway-2`) and one revoked key (`openclaw-gateway-1`).
- Operational health passed after cutover: authority/replay/security-audit/orchestration-audit SQLite integrity was `ok`, backup/restore proof passed, restored counts matched, no expired-active delegation remained, and one active trusted signing key remained.
- Security-sensitive state remained mode `0600`.

## Public-key metadata

Replacement public-key fingerprint:

```text
fb6612b03009b2cecca812458ac35c75fd3d4f23efa29ed631e905ff03d235b7
```

Replacement public-key host location:

```text
/var/lib/jason/openclaw/trusted-keys/openclaw-jason-ed25519-v2.pub.pem
```

The corresponding private key remains only inside the OpenClaw persistent secret boundary:

```text
/home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem
```

The old private key remains inside the same OpenClaw secret boundary only for the governed rollback/retention window; Jason no longer accepts its signatures.

## Verification-script correction

The post-cutover operator block initially checked the replacement public key at `/var/lib/jason/openclaw/openclaw-jason-ed25519-v2.pub.pem`. That path was incorrect. The key was intentionally created under the trusted-key directory shown above. The resulting missing-file message did not invalidate the completed cryptographic cutover, governed execution proof, revocation proof, or operational-health result.

## Boundary confirmation

This rotation did not create or expand JKD-001 authority, did not expose private signing material to Jason state or Git, and did not contact any external provider.
