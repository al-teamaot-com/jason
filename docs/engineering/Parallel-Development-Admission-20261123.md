# Parallel-development admission | source engineering candidate

## Purpose

Prevent concurrent engineering from modifying the same files, components, contracts, providers, schemas, deployment mechanisms, authorization paths, or shared tenant scopes. Preserve independent source work while production drift checks continue to compare **only** protected production desired state against observed production state. Git branches, worktrees, open PRs, and staging outputs must never be treated as production deployment drift.

## Implemented in this candidate

- Reuses `tools/dependency_conflict_service.py`; keeps its existing `analyze()` advisory interface unchanged.
- Adds `admission(candidate, existing, production_healthy=...)`, a deterministic, nonmutating, fail-closed decision helper.
- Detects file and semantic-domain overlap; explicit upstream dependencies remain blocked until `production_verified`.
- Missing scope declarations, invalid inventory, unknown workstream types/states, and unverified feature-production health block admission.
- CLI accepts `--candidate`, reads the inventory at `--input`, and writes an explicit JSON decision at `--output`; exit 0 permits development admission and exit 2 denies it. The older advisory CLI remains available without `--candidate`.
- No deploy, runtime mutation, gateway modification, breaker change, credential access, or provider writes.

## Remaining integration gates

1. Bind the Owner-approved development worker's **claim transaction** to this admission result, with durable locking and current inventory to prevent simultaneous workers racing through the same decision. Do not infer admission from board display or issue title.
2. Collect authoritative semantic declarations from approved workstream metadata and file changes, including explicit upstream revision identities. A missing declaration must fail closed rather than allowing concurrency.
3. Include conflict/blocked/resume state and references in the Development & Release Control Board. Recheck blocked work automatically after exact upstream verified acceptance and current-main reconciliation.
4. Test concurrent claim races, interruption/retry, overlap beyond files, tenant isolation, stale branches, and independence from production drift.
5. Prepare exact source/rollback scope and seek applicable governed production authorization. Validate live postdeployment acceptance without restarting unrelated Core services.

## Important boundary

Source tests do not prove the control is installed or used by the live work scheduler. Until durable claim-path integration is verified, normal workstream admission behavior is unchanged. The existing production freeze and protected release policy remain controlling.
