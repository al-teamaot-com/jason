# Catalog-only unsigned offer source refresh and PMv4 rollback guard (2026-11-19)

## Incident
The exact Owner release script refused `OFFER_STALE_PROTECTED_MAIN_CHANGED` because PMv4/playbook merges moved protected `main` after the catalog-only offer was staged. The original offer `release-755fa5fe3f75958f` binds candidate `755fa5fe3f75958fee2427a0af0777dd242d8f00`, original rollback `d1b8c196dadd4b672ec8ba47075f27bb61c98d63` and the unchanged runtime/MCP image IDs.

The production breaker remained closed; no signed catalog approval, production image promotion, Autotask provider write or PMv4 change occurred.

## Durable minimal correction
Update only the **already installed catalog root request module** `tools/catalog_scoped_promotion_root.py`. Its existing source-only `catalog_scope_stage` action may refresh an **unsigned** offer after a descendant protected-main commit, but only if all fields except `protected_main_sha`, its newly computed immutable admission receipt, and its manifest digest are *identical*. It requires exact root/public offer byte agreement; no Owner signature, prior transaction, active overlay or previous consumer record; root protected source admission and CI checks; frozen production marker; native release lock; preserved original as root-owned audit evidence; atomic root/public replacement and exact rollback on failure. Other changes or concurrent PMv4 source movements fail closed. No signed approval is inferred.

The same catalog root host subclass now captures Ticket Processing and Runbook Management state at the start of the **existing native catalog promotion transaction**, including Ticket Core and Shadow Gateway container identity/health, Runbook Management PID/state, and JSON playbook registry count/generation. Its `verify_unchanged_protected_containers` is invoked after each image activation **inside** `promote_scoped_catalog_pair`'s existing try/paired-rollback handler. Thus a PMv4 health regression is an acceptance failure that triggers native two-image rollback before `production_pair_verified` is recorded. The independent PMv4 services are never deployment targets.

## Root installation boundary
`tools/catalog_root_unsigned_offer_restage_install_once.py` is a source-only, separately authorized one-use installer. It permits **one exact root-owned module update only**, not a freeze removal, systemd change, runtime/MCP promotion, or provider write. It requires protected-main branch and completed required CI, exact original module SHA, exact updated module SHA, unchanged root release worker/policy, original images, freeze, breaker and independent PMv4 health, absence of any signed Owner approval or catalog deployment attempt, both existing root release locks, and fresh Entra Owner login and typed exact-action confirmation. It writes durable Owner audit and original bytes before installation; verifies the native root trust loader and all six protected containers afterward; and restores original bytes on failure.

The existing canonical signed-release approval issuer and native Production Manager still govern the subsequent image promotion. **This root source change does not create approval.**

## Tests and acceptance criteria
Tests must cover successful unsigned restage, all disallowed candidate/rollback/image/permission changes, approval/transaction denial, root/public mismatch, parent-main divergence, preserved exact root audit, atomic-public-write failure rollback, strict root action routing, PMv4 pre/post parity and rollback exception, and the synthetic one-use Entra Owner installer success/rollback. GitHub required workflows and production read-only admission must pass before the interactive Owner root action.

A source-only staged offer is not production deployment. Final proof requires both candidate images running, original freeze restored, exact signed one-use approval consumed, independent PMv4 services unchanged and healthy, and no new Autotask writes without separate grants.
