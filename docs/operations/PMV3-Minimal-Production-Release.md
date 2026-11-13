# PMv3.1 — Minimal Production Release

This document replaces the retired duplicate CCC operational instructions. It is an engineering simplification, not permission to bypass the Project Jason Governance Handbook.

## One release path

1. **Build** one immutable runtime/MCP artifact for an exact protected-main SHA. Inventory its complete change scope.
2. **Validate** targeted and foundational regression, applicable protected security checks, a production-equivalent isolated preproduction test, image digests, current production health, and the verified rollback SHA. Apply the risk-based independent-review policy only when the candidate materially changes a protected authority/security boundary. A failed required check is a stop.
3. **Approve once** with the exact SHA, reviewed scope, rollback SHA, manifest fingerprint, approver identity and timestamp. The same exact Owner decision is the one-transaction release authority. No second unfreeze decision and no second CCC human review.
4. **Deploy** through the native locked Production Manager transaction. While the legacy freeze marker remains during migration, Production Manager opens/restores it internally from the exact release transaction binding; it is not a second Owner authorization.
5. **Verify** live runtime/MCP/host alignment and immutable image identity, functional smoke, ticket-processing continuity, protected drift, and complete production manifest. Restore freeze automatically; use the pinned rollback on failure and verify rollback before clearing the breaker.

## Risk-based independent review

Separate independent review is required only when the candidate materially changes authority/identity, cryptographic trust, root/credential privilege, tenant/client or information-release isolation, release break-glass/protection, or provider-write/autonomy scope. Merely touching PMV3/release files or receiving a `production_control_core` classification does not itself create another human review requirement. See `docs/operations/Jason-Risk-Based-Independent-Review-20261110.md`. Protected security CI and the normal exact release evidence remain mandatory for every applicable release.

## Removed complexity

The PMv3.1 release path no longer runs separate CCC certification preflight/postflight, creates duplicate CCC material-review approval, or requires a second Owner unfreeze decision. New normal releases also do not issue replacement-unfreeze or initial-unfreeze-renewal approval cards. Grafana assurance and dashboard installation are independent monitoring operations, not required release admission or rollback decisions. PR documentation-impact declarations and strict site-build warnings are not production gates; essential architecture and release facts remain in canonical Git documentation. Provider identity recovery still verifies runtime/MCP health and actual provider canaries. The native SHA, scope, approval, preproduction, protected drift, transaction lock, technical quiescence, and rollback gates remain mandatory. Historical CCC/unfreeze documents and evidence remain recoverable for audit and migration compatibility.

## Stop conditions

No production transaction if the prior rollback is unverified, circuit breaker is open without a separately approved recovery path, candidate identity or signed Owner approval is stale, release scope changed, foundational health failed, or rollback is unverified. Never silently convert an unhealthy state to PASS.

The eight-service workstream remains separate until it is actually integrated and independently accepted. Source-only fixes and CI success do not authorize production deployment.
