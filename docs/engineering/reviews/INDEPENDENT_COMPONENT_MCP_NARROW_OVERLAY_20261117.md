# Independent component MCP approval — exact live-baseline overlay

**State:** source-only engineering; not approved for production, not deployed.
**Purpose:** Make the reusable independent-component Owner approval tool available without shipping unrelated newer runtime/MCP modules.

## Exact provenance

- Reusable root/controller and approval implementation (reviewed protected source): `675b99e73c33c228a8531c2797eb3db53c399ad8`, merged by protected PR #2525.
- Live MCP rollback image ID: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
- Exact deployed `jason_mcp/server.py` SHA-256: `a2d69adc40c9537046652fecd5c1bd111a8e6ac30f89829c9b0f11c637532d80`.
- Generated overlay manifest SHA-256: `36b4b898399e67844cf85a258dc6f81875b5f0b2359e910758d5cf22f0a7cc3d`.
- Generated server SHA-256: `8e57982f1986dc6cfa70bed1891340f3748ba3c9d27f8d87ad3912beb4f40689`.
- Staged overlay context: `/home/al/.local/share/jason/independent-component-mcp-overlay-675b99e73c33`.
- Immutable **non-deployed** MCP overlay image ID: `sha256:3659daf7242a0850a1c168d3bb444637117a2be88817f3fdaa7503bff391a004`.
- Offline image import smoke: `NARROW_MCP_OFFLINE_HANDLER_IMPORT=PASS`, networking disabled. Running `jason-mcp-pilot` still uses the original image.
- User-approved financial statement artifact remains source `c205bb4ac163e7d433796f2f4839a90c7cc1f56b` and image `sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195`. Do not substitute a mutable tag.

## Scope and controls

`tools/independent_component_mcp_overlay.py` refuses any baseline hash other than the observed deployed server SHA, reads only the two reviewed `675b99e73...` Git blobs, inserts the one new import and decorated endpoint, proves exact patch reversal, stages only four 0400 files under the user's private staging directory, and does not invoke Docker or touch running services.

The overlay Dockerfile inherits a **separately inspected exact base-image ID** from a local pinned tag, copies only `server.py` and `independent_component_release_approval.py`, and does not rebuild the entire MCP source or install dependencies. The composed image must retain the original baseline behavior outside this approved endpoint. Offline import is necessary but not an operational readiness claim.

The first full MCP build of source `675b99e73...` was **rejected for release scope**: its installed `server.py` contained unrelated Microsoft group and catalog-grant changes. Do not deploy that broader image `sha256:adbc4ae24f9ca6474cbdccbdaeeb0348fa4b6b248661c2eec3e14dffe50ceb9d` for this objective.

## Separate release permissions and rollback

This engineering PR and the built image authorize **no production change**. A separately authenticated exact-SHA Owner release-control installation approval must cover the root-owned independent controller, pinned trust/host policy, fresh protected-CI attestation, approval offer delivery, and narrowly scoped MCP image switch. The Owner-ordered production-deployment freeze must remain byte-identical and no shared runtime/PMv4 service may be restarted.

The MCP rollback is restoring image `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477` with verified container identity/health. The root-controller rollback on its *first installation* disables/removes only the new trusted entrypoint and keeps receipts and audit state. The financial-service deployment requires a subsequent separate signed one-use component transaction and real 05:00 operational verification.
