# Production Promotion Non-Production Acceptance

**Issue:** #765
**Parent:** #758
**Environment:** synthetic/non-production only
**Production mutation:** prohibited

This acceptance suite proves the J-CHANGE-003 promotion boundary before any Production activation.

| Required case | Acceptance proof |
| --- | --- |
| No approval | Production plan gate denies with OWNER_APPROVAL_MISSING |
| Wrong approver | Owner trust check denies non-Owner principal |
| Wrong environment | Production-only target check denies candidate/staging target |
| Expired approval | Approval expiration denies execution |
| Replay / consumed approval | Durable continuation and permit claim stores reject reuse |
| Changed plan | Exact plan SHA-256 no longer matches approval |
| Changed artifact/source/config/policy/schema/migration | Material change produces a different plan fingerprint or permit mismatch |
| Unresolved blocker | Matching approval still fails while blockers remain |
| Trusted authority unavailable | Missing trusted signer fails closed |
| Alternate/direct runner bypass | Direct live-container runner requires signed permit; legacy mutators are blocked before first write |
| Failure after approval consumption before apply | Durable continuation remains consumed; retry requires explicit recovery/new authority |
| Post-deploy verification failure | Simulated health failure invokes restoration of prior live container |
| Safe rollback | Prior container rename/start restoration is attempted deterministically |
| Unsafe rollback | Teams rollback rejects changed backup digest before permit claim or live mutation |

## Evidence command

The acceptance tests are intentionally deterministic and do not invoke Production providers or mutate the live Jason host.

Run:

PYTHONPATH=implementation:implementation/runtime_service/src:. python -m pytest tools/tests/test_production_promotion_acceptance.py tools/tests/test_legacy_production_mutators_blocked.py -q

The broader #764 permit/runner suites must also remain green.

## Activation boundary

Passing this suite does not authorize Production activation.

Installing the trusted signer/public-key registry, claim store, or gated Production runners on the live environment requires a separate exact Owner-approved Production promotion.
