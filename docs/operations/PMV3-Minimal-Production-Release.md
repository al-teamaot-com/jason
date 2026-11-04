# PMv3.1 — Minimal Production Release

This document replaces the retired duplicate CCC operational instructions. It is an engineering simplification, not permission to bypass the Project Jason Governance Handbook.

## One release path

1. **Build** one immutable runtime/MCP artifact for an exact protected-main SHA. Inventory its complete change scope.
2. **Validate** targeted and foundational regression, a production-equivalent isolated preproduction test, image digests, current production health, and the verified rollback SHA. A failed required check is a stop.
3. **Approve in Teams** with the exact SHA, reviewed scope, rollback SHA, approver identity and timestamp. One Teams approval should supply any required one-transaction freeze authority; that separate UX correction is tracked in issue #2316 and is not yet deployed. No second CCC human review.
4. **Deploy** through the native locked Production Manager transaction. Preserve the freeze outside that one release.
5. **Verify** live runtime/MCP/host alignment and immutable image identity, functional smoke, ticket-processing continuity, protected drift, and complete production manifest. Restore freeze automatically; use the pinned rollback on failure and verify rollback before clearing the breaker.

## Removed complexity

The PMv3.1 release path no longer runs a separate CCC certification preflight/postflight or creates a duplicate CCC material-review approval. It relies on the existing native source, scope, identity, preproduction, production-health, drift, and rollback gates. Historical CCC implementation and documents remain recoverable in Git history.

## Stop conditions

No production transaction if the prior rollback is unverified, circuit breaker is open without a separately approved recovery path, candidate identity or signed Owner approval is stale, release scope changed, foundational health failed, or rollback is unverified. Never silently convert an unhealthy state to PASS.

The eight-service workstream remains separate until it is actually integrated and independently accepted. Source-only fixes and CI success do not authorize production deployment.
