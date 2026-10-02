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

## Inspection and validation CLI

The non-production foundation now includes:

- python tools/jason_recovery.py inspect PACKAGE
- python tools/jason_recovery.py validate PACKAGE --signer-public-key SIGNER_PEM
- python tools/jason_recovery.py validate PACKAGE --signer-public-key SIGNER_PEM --recovery-private-key RECOVERY_PEM

Inspection exposes only package metadata. Signature validation does not require the recovery private key. Optional decryptability validation decrypts in memory to prove key/package compatibility but does not print recovered member contents.

Export-from-live-state and restore remain intentionally unavailable.

## Restore planning

The recovery foundation now has a plan-first restore boundary.

The encrypted payload carries an internal recovery-state manifest that binds:
- source deployment identity;
- logical recovery state class;
- encrypted payload member name;
- target relative path;
- payload SHA-256;
- payload size;
- non-secret source metadata.

Before any write, the restore planner cross-checks that manifest against the versioned recovery-state taxonomy.

It fails closed on:
- source deployment identity mismatch;
- unknown state classes;
- payload digest or size mismatch;
- missing payloads;
- unmanifested payloads;
- state classes not allowed in a Full Recovery Export;
- reconstructable/discardable state incorrectly carried as restore payload;
- machine-bound identity payloads;
- required re-enrollment;
- unsafe restore paths.

A non-production apply helper can restore a plan only when the plan is ready_for_restore. It writes each payload atomically with private file permissions, refuses existing targets, does not run migrations, does not start services, and does not perform provider re-enrollment.

The live filesystem root remains unsupported by this implementation.

## Restore CLI

The recovery CLI now exposes the non-production restore sequence:

- inspect
- validate
- plan-restore
- restore-to-root

plan-restore decrypts the package in memory, validates the internal recovery-state manifest against the versioned state taxonomy, and emits only the restore plan. It performs no writes.

restore-to-root repeats the same validation and applies only a ready_for_restore plan to a non-live target root. It refuses blocked and re-enrollment-required plans before creating restored state.

Restore output reports state classes, target paths, hashes, and status but never prints recovered secret contents.

## Full Recovery Export collection

The recovery work now includes a collection contract for building a Full Recovery Export from a non-production Jason root.

Collection strategies are explicit:

- file: collect a declared regular file;
- sqlite_backup: create a SQLite-consistent snapshot using the SQLite backup API and verify integrity;
- directory_files: walk a declared durable directory while rejecting symlinks;
- metadata_only: record reconstruction/re-enrollment metadata without copying unsafe state;
- external_adapter: require a governed provider-native exporter for state that cannot be safely copied as files.

Required local state or required adapters fail closed when unavailable. Optional state is recorded as missing rather than silently treated as present.

The default v1 collection contract includes configuration, policy, Deployment Manifest, authority/client-boundary/orchestration/approval-continuation SQLite state, optional playbook/business state, and explicit required adapters for governed provider secrets and signing/recovery key material.

The recovery CLI adds plan-export. This command validates local recovery sources and adapter availability without reading or printing secret values.

A synthetic round-trip acceptance now proves:

source Jason root
→ consistent state collection
→ governed secret/key adapter payloads
→ encrypted signed package
→ decrypt
→ recovery plan
→ explicit machine re-enrollment completion
→ restore to clean root

The encrypted package file is written with mode 0600 and contains no plaintext secret or signing-key content.

## Built-in OpenBao recovery adapters

The Full Recovery Export now consumes Jason's existing governed OpenBao recovery model rather than enumerating provider secret values.

The governed secret adapter:

- selects the newest declared OpenBao Raft snapshot;
- requires the snapshot and checksum sidecar to be private regular files;
- verifies the snapshot SHA-256 before inclusion;
- places the snapshot and checksum only inside the encrypted recovery package.

The governed key adapter:

- requires the protected OpenBao initialization artifact to have private permissions;
- validates the recorded Shamir recovery structure without printing any share or token;
- packages the protected initialization artifact only inside the encrypted recovery package;
- includes trusted-key registry/material from the canonical Jason trusted-key directory when present.

The recovery CLI now exposes export-from-root for non-live roots. The command requires an X25519 recovery-recipient public key and Ed25519 signer private key, writes the resulting package atomically with mode 0600, and emits only non-secret summary metadata.

The implementation still refuses export-from-root when target-root is the live filesystem root. Production export activation remains a separate exact-plan Owner-approved operation.
