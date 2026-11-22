# PMv4 Stage E: live isolated A1 shadow acceptance readback

**November 18, 2026. Source-only retirement evidence, not retirement authorization.**

The authenticated one-owner v5 shadow recovery reported
A1_ONE_OWNER_FULL_SHADOW_RELEASE=VERIFIED_POSTFLIGHT, with exact source
9859463e5255ecf7040de21d73e9f4062b46a18e and root Owner approval
owner-mcp-e547ca784f76418391ca5bd938afd237. The live independent
host readback subsequently verified:

- Root-owned current symlink points to the exact v5 release.
- The isolated shadow gateway is running, healthy, not OOM-killed.
- Effective memory cap is exactly 4294967296 bytes (4 GiB).
- OCI image ID is the same previously accepted SHA-bound image
  sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd.
- Docker network mode is exactly none.
- Ticket Core remains externally hosted, healthy; MCP remains running.
- Existing production freeze, promotion hold, breaker and drift remain unchanged.

The Stage E read-only attestor now observes exactly one reviewed A1
shadow container via a fixed allowlisted Docker format: health, memory
bytes, SHA-bound image, running and network mode. It additionally
requires a root-owned symlink with exactly the accepted v5 release
SHA; foreign pointers fail closed before Docker inspection. Any changed
image/memory/network/state denies the live A1 gate. It does not invoke
Docker start, stop, restart, delete, or Compose.

The A1 root-only immutable acceptance receipt is a **separate gate**,
and this unprivileged readback marks it unverified until a trusted
root-only retirement preflight checks the actual signed receipt and
audit chain. A1 live success is not proof of generic independent
component-release-controller parity or replacement engineering
scheduling. The existing PMv3 user timers, root release timers/path,
monitoring/boot safeguards and desired-state policy remain required
and unchanged.

Tests reject wrong OCI SHA, wrong memory, bridge network, unhealthy,
nonrunning and missing containers, untrusted/changed root pointer,
unallowlisted Docker operations and any attempt to claim PMv3
retirement from shadow health alone.

**Live disposition:** A1 shadow is healthy, Stage C external worker
healthy, Stage D read-only service healthy. Stage E remains NO-GO
until independent root acceptance readback, replacement-controller and
engineering-scheduling parity, desired-state transition review,
and fresh exact authenticated Owner retirement release.
