# Independent component controller — minimum governed installation

**Status:** Source-only pending protected CI, fresh exact Entra Owner signature and SHA-pinned root execution. This does NOT deploy or activate the financial scheduler.

## Scope reduction

The Owner requested the smallest path to a working independently signed component-release control after the authority-health incident resolved. The approved narrow MCP overlay image is **not necessary for the root controller**: issue a separate Entra Owner-signed, exact-action approval against a prepared root-owned offer using Jason's existing pinned Owner signer. Keeping the live MCP unchanged preserves the existing protected last-known-good image and avoids a new native mixed runtime/MCP transition. The previously approved overlay is not revoked or silently deployed; it stays staged for a future independent review if required.

## Exact installer boundaries

- Controller source commit `675b99e73c33c228a8531c2797eb3db53c399ad8` with six reviewed, pinned SHA256 source blobs.
- Root script `tools/independent_component_control_install_root.py` installs **only** `/opt/jason/independent-component-release/trusted/`, a single pinned root-owned host profile under `/etc/jason/independent-component-release/`, its root-only state/lock/receipt directories, owner-only offer/outbox directories and a disabled financial scheduler state directory.
- Owner consent script `tools/independent_component_control_install_owner.py` uses the currently installed, exact-SHA-pinned Entra device-code signer and service private key as UID 1000; signs a 15-minute, one-use proof bound to this installer SHA, manifest, scope and unchanged frozen state. It does not execute anything as root.
- Before mutation the **isolated, SHA-pinned** root script independently verifies the owner signature with the existing root public key, exact source hashes and root release LKG, clean breaker/production drift, all original protected Docker container identities, freeze fingerprint, and both PMV3/PMv4 transaction lock inodes.
- Root record is claimed before installation. All newly written files read back against approved SHA-256s. On any failure, installed files are removed where safe, and an auditable failed/partially rolled-back one-use root receipt remains.
- It does **not** recreate, stop, tag, or restart any existing container; does not mutate native LKG, production freeze, PMv4, the live authority database, providers or Autotask; does not issue fake CI evidence or owner offer; does not start a financial scheduler.

## Remaining gated work after this install

The controller is installed in **disabled** state with no standing authority. A component-specific approved bundle, fresh protected CI attestation and a separately signed exact financial-service promotion are needed before the independent root entrypoint may activate that one service. The original installation authorization never authorizes financial scheduler activation.

**Not a production acceptance claim:** CI tests and staged code do not establish a successful root installation. Require installed-path/digest readback, root receipt, protected service continuity, and unchanged production freeze after the authenticated Owner SSH step. No passwords or device-code tokens should be posted to ChatGPT.
