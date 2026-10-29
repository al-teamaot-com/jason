# Stage B1: routine human Autotask ticket writes — isolated release preparation

**State:** Draft source candidate only. No protected-main merge, release-manager approval, production deployment, or feature activation. This file is not a deployment authority.

## Baseline and exact retained scope

- Protected production baseline: `d71cde5d24bdd65e67cb5c44d29eaf5f104edcbf` (verified Stage A).
- Extracted from broad draft #2128 (`6fc2b60ea4ee5adff8d615833b548388512ab1b8`) onto a separate clean branch.
- Existing Stage A already implements the human-only matcher and persisted immutable AOT standing grant. Stage B1 **only** supplies safe optional environment propagation to the runtime, MCP, and development Compose with security/roll-back tests.
- Supported capabilities are exactly `service.ticket.create`, `service.ticket.update` and `service.ticket.note.create`. No broad provider grant, no new Autotask license, no added provider credentials, no endpoint/Datto RMM changes, no customer notification action.
- The existing Autotask requester impersonation, provider-native permissions, approval recording for exact intent, short TTL, idempotency, audit, and independent readback continue to apply.
- The runtime opt-in `JASON_AOT_ROUTINE_RW_PROFILE=autotask-ticket-v1` requires a **separate, explicitly authorized** production configuration change under Production Manager. Unset/default/empty is OFF. Unsupported nonempty values reject before deployment.
- Both native production deploy scripts propagate an explicit empty profile by default and force OFF during the baseline rollback, rather than carrying forward a newly enabled standing grant.
- IT Glue configuration-note writes and Entra/Graph user creation are **excluded** from this release; no write AppRoles, policies, secret projections or activation plumbing included.

## Pre-merge source validation

1. Confirm `main` is the exact Stage A baseline and this branch is a clean direct descendant.
2. Compare exact path-level diff and verify it contains no broad #2128 provider changes, worktrees or secrets.
3. Validate bash syntax, Compose defaults, source-policy tests for 3 capability names and human/identity/client exclusions, and existing ticket create/update/internal-note tests.
4. Build exact-labeled review-only runtime/MCP images and run `production-deploy.sh --preflight` with profile UNSET. Ensure running containers remain on Stage A.
5. Run fail-closed negative preflights with invalid profile; separately validate rollback image path forces profile OFF. Never run the scripts without `--preflight` before an exact-SHA deployment approval.
6. Obtain an independent code/security review of the specific B1 diff. Reconcile and rerun exact-head CI. Do not merge unaccepted source changes.

## Post-merge / release-manager acceptance gates (not authorized yet)

- The native Production Manager requires a fully merged, **protected-main** candidate SHA before it can prepare the actual release record. An unmerged PR head cannot be declared production-eligible or deployed.
- Before any exact-SHA deployment request, record full baseline-to-candidate scope (including unrelated merges), reviewed dependencies, immutable images, provider-backed tests, fundamental capability smoke tests and rollback SHA.
- Activation is separately scoped and must not be conflated with deploying default-disabled source. Without activation, live capabilities can remain authority-denied for the requester.
- Live acceptance requires an AOT technician principal and provider-native Autotask Resource mapping; test controlled XYZ Test Company ticket creation, update, and **internal note** with independent readbacks; verify no unauthorized client writes or unintended notifications; preserve preimages for reversible fields; check service principal/foreign/disabled identities fail closed. Ticket creation and note operations require their own exact human authorization and safe provider checks.
- Any failed production health, guardrail, provider-scope or post-deploy verification must trigger the last-known-good rollback, and the global production freeze and auto-promotion hold must be restored.

## Explicit concurrent work reconciliation

- #2125 and #2128 both touch the production runtime/MCP deployment scripts and Compose. They add broad IT Glue/Entra integration that is intentionally **not** copied into this narrow branch. This branch adds one scoped Autotask environment variable and retains the current Stage A deployment behavior and complete original provider-read activation profile.
- #2126 also touches Compose for Windows Time. Its source is not overwritten or merged here; its implementation is retained in stacked #2129. The later Stage C restack must combine its disabled JSON shadow settings with this branch's independent default-OFF Autotask setting.
- All old branches, commits and unaccepted provider adapters remain in GitHub. This branch is an *additive minimal extraction*, not a rewrite or rejection of those changes.
- There is **no independent reviewer approval yet**. A green CI run cannot be treated as a substitute for the separate code/security review and provider acceptance gates.

## Unrelated development and stacked Stage C

Original broad draft #2128 remains intact for later independent IT Glue and Entra work; nothing in that branch is discarded. Stacked Stage C #2129 remains unchanged while its JSON read-only pilot is reconciled against the final accepted Stage B1 merge result. Stage C is always disabled until separately authorized and verified.
