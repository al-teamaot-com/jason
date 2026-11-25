# PMv4 A1 exact owner shadow candidate v2 — source and acceptance

**Status:** source-only, NOT signed or installed. Protected production freeze,
promotion hold, PMv3 Ticket Core and root-owned A0 code remain untouched.

## Scope and source authority

After the failed original Owner-approved A1 transaction was recovered
under its original single-use rollback consent, protected source PR #2503
was integrated as GitHub `main` SHA
`e7438c3707387764577c059c99c6ac65d9dd2c40`. Its original
Owner approval `owner-mcp-319c697027a146beac98818e5305a971`
is **historical, consumed and rollback-only**.

The first integrated source acceptance found three defects missed by
the earlier source profile tests:

1. The separately installed A0 root-owned Compose file still uses 512 MiB,
   64 PIDs, 0.5 CPU and 60-second startup; changing a source file alone
   does NOT update the runtime used by DockerShadowAdapter.
2. DockerShadowAdapter's runtime ownership check still strictly allowed
   only 512 MiB / 64 PIDs / 0.5 CPU, so a correctly provisioned
   2 GiB / 256 PIDs / 1 CPU gateway would be denied.
3. The 90-second default shadow health deadline was shorter than
   the 120-second Compose startup window, guaranteeing premature rejection
   for otherwise valid slow initialization.

## Minimal governed correction

The adapter now selects **only the immutable candidate release's own**
`bundle/config/pmv4-shadow/docker-compose.yml` for `docker compose up`,
after independently verifying it against the manifest's SHA256 and
root-owned, mode-0400 metadata. It NEVER overwrites the protected A0
Compose file. On rollback to the original empty baseline, the original
root-owned Compose continues to be used solely for `docker compose down`
of the exact isolated project, without deleting its state volume.

The runtime attestor now accepts exactly 2 GiB, 256 PIDs and 1 CPU, while
rejecting the previous resource limits and any unexpected broader budget.
The bounded default health wait is 210 seconds (maximum 300), adequate
for the 120-second start period and subsequent independent health probe.
All network, read-only filesystem, drop-all-capabilities, no-new-privileges,
UID1000, no-ports, no-provider-credentials, one-volume and Ticket Core
continuity controls remain unchanged.

## New immutable release from exact protected main

`tools/pmv4_a1_v2_immutable_builder.py` is an offline candidate
generator. It reuses GitHub's final protected-main source-only A1
root/Owner/launcher templates, verifies required main push CI and exact
source file SHA, and renders **three newly versioned and SHA-bound**
artifacts. It creates them only inside a new exact
`/srv/jason/archive/engineering-artifacts/pmv4-a1-<NEW-SOURCE-SHA>`
preproduction packet, which itself must be produced through the
existing `pmv4_shadow_candidate_packet.py`.

The deterministic generated root installer:
- requires the unique new root installer SHA and `/run` stage;
- uses a new one-release action identifier, unique hash-derived audit
  path, new source SHA and new isolated image label/digest;
- requires the native journal contain *only* the single previously
  rolled-back original A1 approval before allowing another empty-baseline
  bootstrap, and preserves all historical receipts/audit;
- independently binds candidate source Git blobs to protected main
  **before** loading executable source-derived host modules;
- verifies the exact reviewed `pmv4_host_release_guard.py` and
  `pmv4_shadow_docker_adapter.py` bytes in memory against the new
  immutable manifest and signed scope, rather than silently continuing
  to call the older A0 root-owned adapter;
- uses the same existing root-pinned Owner Ed25519 verification,
  dual native release locks, immutable first-Owner proof, source/manifest
  and freeze hash checks, fail-closed rollback and health gates;
- never consumes the previous Owner approval as authorization for a
  new source, manifest, image, scope, or release.

The generated launcher validates exact script hashes, pinned source
checkout, plan and evidence, freeze/hold and expected production LKG;
root-only preflight must pass before issuing a **new** authenticated Owner
challenge, which is not yet requested.

## Source acceptance evidence and limits

Source-only tests demonstrate exact template rendering, duplicate/altered
template denial, old-consent non-reuse, current source and image hash
binding, new audit and root staging separation, immutable Compose
selection/tamper denial, strict 2 GiB/256-PID/1-CPU resource acceptance,
old/expanded resource rejection, 210-second bounded health budget,
Docker 29 missing-object behavior and existing cross-release lock and
native rollback safety. Docker Compose syntax and final local OCI image
identity must also be confirmed after integration of this corrective PR.

**Not yet satisfied:** new final merged-main SHA, final local image with
matching source label, generated immutable candidate bundle/release
manifest/Owner plan, privileged preflight, actual isolated running gateway
health/resource headroom, active source/receipt recovery on failure, and
end-to-end independent acceptance. None of those facts can be inferred
from passing source tests. The previous production image was removed
under its approved rollback and must not be promoted again.

A controlled root preflight is required before another Owner ceremony.
Do not allow another failure *after* Owner signing that could have been
caught by the available source, root and resource probes. C/D/E remain
separately governed stages and no authority for them is granted here.
