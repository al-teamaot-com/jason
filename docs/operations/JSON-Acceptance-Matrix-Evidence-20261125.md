# JSON acceptance matrix evidence correction

The shared source-only matrix previously aggregated test counts by candidate
and shared suite. A skipped test, or a missing test module masked by a passing
sibling module, could leave its synthetic acceptance result passing. A reused
JUnit output path also made stale evidence possible when an invocation failed
to produce new results.

Require nonzero executed passing tests in every expected module, zero skips,
errors and failures, no unexpected module, and the existing 19 exact immutable
draft-reopen probes. Keep each test invocation's JUnit and result receipt in a
separate private run directory. Publish a pending status before pytest starts
and an atomic final status; missing/malformed JUnit and test timeout publish
failure. CI independently checks the counts and the selected run receipt.

November 25 verification against main e73d282e0f2526e1a7a819120900a24c9f9b20bf:
27 focused governance/evidence tests passed. All 29 required source-test modules
ran, with 546 tests passed, zero failures/errors/skips, and 19/19 candidate
source and immutable draft-reopen probes passed. Evidence is retained under
/srv/jason/archive/engineering-artifacts/json-acceptance-matrix-evidence-20261125-pDPq87Te.
The isolated test registry override avoids the live Datto approval registry.
No production registry changes, provider calls or legacy retirement occurred
during these synthetic suites.

This is verification hardening, not a migration approval. Full live behavioral
acceptance remains 0/19. The existing provider-test target boundary remains
unchanged. Native endpoint diagnostics conducted independently through existing
governed read capabilities are not substitutes for independently authenticated,
exact isolated provider-test tenancy and action receipts.
