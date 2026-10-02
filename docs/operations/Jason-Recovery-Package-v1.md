# Jason Recovery Package v1

Issue #789 defines the encrypted full-fidelity recovery package.

The current implementation is a non-production package-format foundation using synthetic data only.

## Cryptographic envelope

- Recovery payload is archived in memory and encrypted with a random AES-256-GCM data key.
- The data key is wrapped for an X25519 recovery recipient using HKDF-SHA256 plus AES-GCM.
- Package metadata and encrypted payload are signed with Ed25519.
- The encrypted payload carries an independent SHA-256 digest.
- Recovery-key and signer-key IDs are explicit metadata.
- Secret payload content is not exposed by package inspection.

## Current operations

The library supports:

- package creation from explicit byte members;
- metadata inspection without decryption;
- signature/integrity verification;
- decryption and safe member extraction.

## Current limits

This foundation does not yet read Production state, export OpenBao, stream large databases, manage Owner recovery-key custody, or restore onto a live host.

Those operations remain blocked until state classification, consistency, key-custody, and restore planning are complete and separately validated.
