# PMv4 A1 v5: verify exact reused OCI identity without false source label mismatch

**Source-only, November 18, 2026. No production mutation.**

The v5 existing-release shadow recovery intentionally reused the approved,
content-addressed OCI image sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd.
That image was built for the prior accepted shadow revision
75f2b4c0c48a15bd17d700b9f039fe56623e3f52. The immutable OCI label
com.aot.jason.source_revision therefore equals that prior revision, NOT the
new 8a23b33901536edb3d21c4535bce4f2d93ab6ec9 source-only Compose
revision.

The generated v5 privileged root preflight inherited the first-install
requirement that the OCI source_revision label equal CANDIDATE. Thus the
actual read-only preflight emitted A1_SHADOW_IMAGE_NOT_REVIEWED before Owner
authentication, despite having already verified the exact image digest and
all earlier root gates. No Owner proof or production mutation occurred.

The correction is limited to the reviewed v5 root renderer. Its exact
reviewed-reuse predicate now requires ALL:
- one real Docker image record with Id exactly equal to the signed IMAGE;
- IMAGE equals the previously accepted PRIOR_IMAGE content hash;
- component = pmv4-shadow;
- lifecycle = preproduction-only;
- production-core = excluded;
- provider-mutations = disabled;
- source_revision = the exact pinned prior accepted ROLLBACK SHA.

Wrong digest, missing or duplicated records, absent labels, changed provider
mutation or lifecycle markings, arbitrary or new source revisions all fail
closed. The first-install root verifier is not changed. Existing immutable
root receipt, prior audit and token, root source, release scope, native
Docker isolation, 4 GiB actual-memory readback, host freeze, release locks,
breaker, authentic Owner decision and stopped 2 GiB rollback remain required.

The generated pure predicate was run against the real local Docker OCI
inspection and passed without starting or modifying the shadow container.
Expanded regression: 163 tests and 44 subtests pass, including negative
security-label/digest tests.

The previous v5 command refers to an immutable old root hash and MUST NOT
be rerun. A new protected-main SHA, immutable plan and exact one-use Owner
approval are required before a production activation.
