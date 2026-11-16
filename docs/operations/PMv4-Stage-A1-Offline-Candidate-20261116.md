# PMv4 Stage A1 — independent shadow release package (source only)

**Status:** Immutable **preproduction** artifact created, not activated or approved. It is NOT a production release or evidence that broader PMv4 is operational.

## Verified starting state — November 16, 2026

- Owner-authenticated A0 three-stage native bootstrap completed with full privileged postflight, under source `8c2064193d74cc41b52369681febbc0a74fa96f7`. Original production LKG remains `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- `/var/lib/jason/pmv4-shadow` has the initial empty `0000000000000000000000000000000000000000` baseline, root-owned control locks and signed decision directory. The initial shadow gateway has **not** been started.
- The existing MCP A0 installer issuer remains enabled, but `JASON_PMV4_OWNER_ISSUER_ENABLED=false`. There is **no** live A1 Owner decision.
- The isolated shadow root still lacks a root-provisioned `approved-manifest.json`, `reviewed-scope.json`, candidate release staging, and exact Owner issuer enablement.
- Independent non-mutating `pmv4_shadow_host_runtime.py inspect` reported healthy production Core, protected release ready and `shadow_promotion_ready=false`; the current non-root inspector cannot establish a held privileged cross-release lock.
- Existing original production runtime/MCP images, production freeze/hold and ticket service remain unchanged.

## Reused release code, not a second approval system

`tools/pmv4_shadow_candidate_packet.py` packages **only eight explicit protected Git source files**, building the already defined `ShadowController` release manifest, scope and byte hashes via existing `pmv4_shadow_release.py`, `pmv4_shadow_ci.py` and the canonical Owner signature serializer. It does **not** sign, stage in the root-owned live control tree, call Docker up, touch ticket data, or grant any release authority. Its output is under the unprivileged fixed `/srv/jason/archive/engineering-artifacts` directory. It refuses an unverified protected-main SHA, an unpinned OCI image ID, an existing/unsafe target, and a modified source blob.

The locally built, disconnected-only *preproduction OCI candidate image* is derived offline from the already present `openclaw:local` base digest `sha256:6fdd46f654a1c4edf3ddc7324ebb5918738a35b3e36809c4a47292b399aa7824`. The new **non-running** image ID is `sha256:dab111f8d5d6856120ca6bfb5cbd57858a11f3fe2464c4a2cf53ba88cad8a753`. The source-only Dockerfile introduces identity/isolation labels but no network calls, model API credentials, source or secret mounts, service restarts, or provider actions. Independently verified running Docker container identities and production freeze/hold hashes were unchanged after the image build.

## Immutable preproduction packet

- Source protected main SHA: `8c2064193d74cc41b52369681febbc0a74fa96f7`.
- Output directory: `/srv/jason/archive/engineering-artifacts/pmv4-a1-8c2064193d74cc41b52369681febbc0a74fa96f7`.
- Bundle SHA256: `ddf5b41143036efbb12afcb2bd27f0c4a74081df562248eba551174f3f48a809`.
- Reviewed scope SHA256: `0ea879291cfd875e0cba79b03ed3963cff95cde74ff8f1d1de39b3da6d4833d2`.
- Release manifest SHA256: `3100e8834b6469965cc2a808b83b36e5eafb2c5892f2c6996ad891e4714348d6`.
- Rollback: **initial empty-shadow baseline**, not the existing production runtime.
- Status: `preproduction_candidate_not_authorized`. There is no production root write or shadow container startup.

## Remaining governed acceptance for A1

1. A separate immutable and reviewed trusted **root A1 packet installer** must stage exactly the agreed manifest, scope and bundle, pin the local OCI digest, validate the live root control tree and lock lineage, and return those objects to original absence if any step fails.
2. Verify the Owner issuer through the existing Entra OAuth + Ed25519 trust, activate only the exact independent shadow release scope, and bind one fresh authenticated Owner approval. No Teams approval required. A0 approval may not be reused.
3. Pass two-sided host health/lock and Ticket Core continuity checks, disconnected shadow OCI runtime healthy startup, no paid AI/model fallback, one-time durable release receipt and exact empty-baseline rollback without touching other Docker projects.
4. Keep the global production freeze, promotion hold, original runtime/MCP and all provider integrations unchanged. Independently verify production functional workflows and no new failed services.
5. After further PMv4 stages are proved, continue B (embedded lock), C (external worker), D (independent JSON Runbook Management), E (PMv3 retirement) and other full-outline requirements. **Do not call PMv4 complete at A1.**

No authorization is requested or consumed by this document or source-only candidate.
