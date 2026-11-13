# OpenClaw Workboard — governed J-Man/J-Dev activation

## Purpose and authority

Enable the bundled OpenClaw Workboard plugin for J-Man/J-Dev without creating a separate release or approval system. The existing Project Jason Release Manager owns the source SHA, production-freeze exception, serialized production transaction, signed Teams owner decision, preproduction, CCC, verification, rollback, and immutable evidence.

The production approval recipient is the **admin_approver_separated** Teams owner identity, not the ordinary requester. An ordinary chat instruction, informational Teams message, or synthetic card is **not** release approval. Workboard dispatch and autonomous engineering remain OFF while the engineering Owner pause remains active, even after plugin activation.

## Required two-stage release

1. **Bootstrap source support:** Merge and release the exact reviewed Release Manager change with `config/openclaw-workboard-activation.json` set to `off`. This installs the source-bound Workboard release helper, tests and rollback-aware host controller under the existing signed Teams and production-freeze gates. The gateway configuration does not change. Historical source rollback remains supported.
2. **Bounded activation revision:** Once the bootstrap is deployed, review a separate immutable GitHub revision that changes *only* the source activation declaration to `j-man-j-dev-workboard-v1`, containing the exact current gateway image ID, baseline configuration SHA-256, candidate configuration SHA-256, identical rollback configuration SHA-256, and separately reviewed scope SHA-256. The existing Production Manager validates the live baseline, pin, policy, and preprod; **only then** may Jason Approval Bot issue an exact signed Teams card, including the one-transaction freeze exception. This revision must be current on `origin/main` with protected CI and CCC evidence.

## Transaction acceptance

The native manager under its existing production transaction lock must verify the exact Teams owner grant and release ID, the source Workboard declaration, baseline config SHA, reviewed candidate SHA, immutable gateway image ID and native preflight result.

If eligible, it writes a mode-0600 rollback backup and durable journal, changes *only* the two Workboard plugin JSON fields, restarts the exact existing gateway with `docker compose --no-build --force-recreate`, verifies gateway health, exact image/config hash, and read-only Workboard command availability. It performs no Workboard automatic task dispatch and adds no API-key fallback.

A failed restart, wrong image, incorrect config or unavailable Workboard plugin must restore the exact baseline config and restart once for rollback health. An interrupted in-progress activation is identified from its durable journal and prior signed native release record under the manager's existing lock, and is rolled back to the signed baseline rather than retried. A fully closed activation is only marked committed after verifying its exact reviewed live state. Unknown drift, forged approval, missing records, or damaged backups fail closed.

Successful gateway activation does **not** authorize autonomous engineering, repo publishing, production releases or other disruptive operations. Those require their distinct governed authority and acceptance.

## Evidence, known constraints and boundaries

The initial private configuration package has:

- baseline/rollback SHA-256: `30c1be3be384bf40c65cf19e8a8405eb218693298e814c869ae38587ec7508cc`;
- candidate SHA-256: `a453e212a434ef6d5d105df25d8efd7fd8a8779213cc06eb69da454a266b5ed0`;
- reviewed scope SHA-256: `7a2610512529c12b1baaf18e9e615b5d0de4bed2db765b73ae81f8fa8de95a6e`;
- gateway image ID: `sha256:6fdd46f654a1c4edf3ddc7324ebb5918738a35b3e36809c4a47292b399aa7824`.

These identifiers bind the staged candidate, **not** standing deployment authority. The private complete OpenClaw configuration is intentionally excluded from Git.

OpenClaw Workboard was validated in an offline network-disabled lab: persistent task records, native scheduled dispatch, safe stale-claim blocking, and preserved evidence across restart. Successful real-world autonomous recovery is not yet verified. Production OpenClaw is 2026.7.1 and the gateway remains unchanged until exact release authorization.

**Live preproduction disk condition:** The Jason host root filesystem reports about 2 GB available, causing existing bounded SQLite snapshot tests to refuse operation. Do not reduce the configured disk-reserve guard or attempt production deployment until adequate capacity has been independently verified.

## Status contract

- Source implementation and isolated tests: reviewable engineering evidence, not deployed.
- CI passing: source eligibility, not live approval or production release.
- Valid Teams Approval Bot card: requires the exact current GitHub main candidate and source-backed native release record; only a signed, identity-verified Owner action binds authority.
- Production readiness: requires native preproduction, CCC, exact existing freeze scope, rollback readiness, current disk-capacity checks, and signed Teams receipt.
- Operational completion: requires post-restart gateway, Teams channel, subscription OAuth, existing Jason agent, Workboard plugin and rollback checks with immutable evidence.
