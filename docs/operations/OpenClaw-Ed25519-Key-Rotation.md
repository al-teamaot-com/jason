# OpenClaw Ed25519 Signing-Key Rotation

## Purpose

Rotate the OpenClaw -> Jason machine signing key without creating a trust gap, exposing private signing material, or bypassing the existing OpenClaw ingress, JKD-001, governance, or Central Orchestrator boundaries.

## Rotation model

Rotation is **overlap-first**:

1. keep the current key active;
2. generate the replacement private key only inside OpenClaw's persistent secret boundary;
3. derive/export only the replacement public key to Jason;
4. register the replacement public key with a distinct key ID;
5. prove both old and new keys authenticate while both registry records are active;
6. move the active OpenClaw signing configuration to the replacement key;
7. prove the replacement key succeeds through the governed synthetic path;
8. revoke the old Jason public-key record;
9. prove the revoked old key fails and the replacement key remains accepted;
10. refresh operational health, CatchMeUp, and rotation evidence.

At no point should both keys be unavailable to Jason.

## Production locations

Current OpenClaw private-key boundary:

```text
/opt/jason/services/openclaw/data/auth-profile-secrets/jason-ingress/
```

Mounted in the OpenClaw container as:

```text
/home/node/.config/openclaw/jason-ingress/
```

Jason trusted public-key state:

```text
/var/lib/jason/openclaw/trusted-keys/
/var/lib/jason/openclaw/trusted-keys/registry.json
```

Replacement public keys must remain inside the trusted-key directory. For the first production rotation the replacement path was:

```text
/var/lib/jason/openclaw/trusted-keys/openclaw-jason-ed25519-v2.pub.pem
```

Do not validate or store the replacement public key one directory higher at `/var/lib/jason/openclaw/`.

Private keys must never be copied to `/var/lib/jason`, Git, normal logs, evidence, chat, or command output.

## Required controls

- new key ID must differ from the previous key ID;
- replacement public-key fingerprint must be explicitly pinned during registration;
- registry must contain at least one active key at every stage;
- old-key revocation occurs only after replacement-key verification succeeds;
- registry and public key files remain owner-only (`0600`);
- no provider API or provider credential is required for rotation;
- proof tooling must use only the synthetic health capability;
- key rotation cannot grant authority or alter JKD-001 grants/delegations;
- failed proof stops before old-key revocation.

## Proof tool

Use:

```bash
python3 tools/openclaw_ed25519_rotation_proof.py \
  --old-key-id openclaw-gateway-1 \
  --old-key-path /home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519.pem \
  --new-key-id openclaw-gateway-2 \
  --new-key-path /home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem
```

Before revocation, the tool must report both keys accepted. After revoking the old public-key record, rerun with `--expect-old-revoked`; it must report the old key rejected and the new key accepted.

The signing implementation must use the same recursive canonical JSON contract as `jason_openclaw.signed_transport.canonical_signed_payload()`: all object keys, including nested objects, are sorted before compact UTF-8 JSON serialization. A top-level-only sort is not sufficient.

## Stop conditions

Stop immediately if:

- replacement private key leaves the OpenClaw persistent secret boundary;
- replacement public-key fingerprint does not match the value calculated from the exported public key;
- replacement-key verification fails;
- active trusted-key count would fall below one;
- registry permissions become broader than `0600`;
- any provider API or provider credential is involved;
- the old key is revoked before replacement continuity is proven.

## Retirement

After successful rotation proof, the old private key may remain temporarily quarantined within the OpenClaw secret boundary for rollback evidence, but it must not be used for signing. Final secure removal should follow the approved retention/recovery policy after the rollback window closes.
