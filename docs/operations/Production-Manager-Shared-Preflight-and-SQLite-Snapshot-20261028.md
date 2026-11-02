# Production Manager P0: shared deployment contract and SQLite snapshots

This change addresses the October 28 release failures that escaped isolated preproduction. It does not loosen the production freeze, owner authority, rollback, constitutional checks, CCC, provider authorizations, or user-disruption rules.

## One release contract

Preproduction and production promotion now call the same `native_deploy_environment` validator. It reads source-declared Autotask and QuickBooks profiles and compares the Autotask rollback profile with the independently observed live Runtime/MCP profile **before deployment**. Runtime and MCP shell preflights receive the exact candidate image tags, source SHA, activation and rollback profiles that production would use. Conflicts fail closed before a production transition.

A sanitized SHA-256 digest of the non-secret native deployment inputs is written to the preproduction evidence. Production rederives and compares this digest before CCC and any active-service replacement, preventing subsequent configuration drift or stale preproduction approval. Diagnostic worker enrollment remains independently validated during deployment; it is not silently expanded by the digest.

The separate CCC material-change owner review remains mandatory for the *exact* approved SHA. The release manager does not infer review consent from CI, preproduction, or unrelated approvals. The existing production freeze stays in force until an exact-SHA one-time owner decision is recorded. Preproduction is technical readiness, not deployment authorization.

## Online consistent SQLite state clone

The live Runtime container's actual `/var/lib/jason/openclaw` bind mount is identified through `docker inspect`. Only this verified bind is used as the SQLite read source; the developer checkout is never a state source. Every selected top-level SQLite database is captured with SQLite's readonly online backup API, including committed transactions in WAL mode. The *isolated copy only* is converted to a self-contained DELETE-journal database.

Volatile `-wal`, `-shm`, and `-journal` sidecars are never individually copied after a stale directory listing. Production databases, process state, and services are never restarted or modified. Large historical orchestration event databases remain excluded under the pre-existing bounded preproduction policy. Other operational data and critical release evidence retain the container-copy path and current safety checks.

The snapshot fails closed on an ambiguous bind mount, missing/unsafe source, source database errors, insufficient isolated disk headroom, over-budget data, or a 120-second per-database backup limit. A partial isolated snapshot is removed on failure. There is no fallback to raw SQLite file and WAL copying.

## Acceptance and release gates

Regression coverage includes exact native deployment arguments, v13/live rollback mismatch rejection before scripts run, configuration-drift digest detection, independent Runtime/MCP scripts, SQLite committed-but-uncheckpointed WAL data, missing temporary sidecars, disk constraints, and cleanup. A read-only live database canary confirmed an intact private snapshot without journal sidecars; this did not change production data.

After merging, the candidate still requires protected CI, isolated preproduction, a fresh full change-impact review, exact owner approval plus CCC material review, native production promotion, live health/source/canary checks, rollback on failed acceptance, and freeze reinstatement. No production deployment is authorized by this source change alone.
