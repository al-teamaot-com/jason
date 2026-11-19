# Project Jason — Licensed Owner authority separated from Microsoft administration

**Change classification:** High-risk identity/authorization production-source correction.
**Owner directive:** `al@teamaot.com` is Jason's Owner for authorization and approvals. `al_admin@teamaot.com` is solely the Entra/Azure/Microsoft 365 administrative identity for Microsoft administrative work, never a prerequisite to signing into Jason. Jason executes its own provider actions using Jason's independently governed service principal. Teams approval is not required.

## Verified live state — November 19, 2026

The running `jason-mcp-pilot` uses legacy Owner profile (empty `JASON_AOT_ADMIN_APPROVER_PROFILE`) with `JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-al`. The active, unscoped licensed Jason Owner Entra binding for the regular account is `person-entra-bee80bdcffb04c50b453c09d4d411f5f`, while `person-al` is currently bound to `al_admin@teamaot.com`. The current MCP authorization therefore rejects normal Owner-admin tasks with `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`. This is a **wrong policy design**, not proof of a broken email/login or missing Entra identity. Independent Microsoft Graph directory read confirms the licensed Owner object ID. No account, OAuth credential, Entra role, SQL binding, or provider secret has been changed.

## New exact, source-gated Owner profile

An opt-in `jason-owner-v1` profile accepts only the existing signed and verified Entra account with AOT tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`, object `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`, active unscoped Jason principal `person-entra-bee80bdcffb04c50b453c09d4d411f5f`, assurance `entra-oauth-bearer`, and organization `aot`. Email strings, conversation text, membership in the AOT tenant, an unsigned token, the admin Entra object `c848022d-e13b-4457-84b0-e2f5c00dcaf6`, and client-scoped credentials convey no Jason Owner authority.

The explicit reviewed source manifest is `config/jason-owner-authorization-profile.json`. Its exact claim and organizational bindings are checked against immutable constants by `tools/jason_owner_auth_profile.py`; missing historical manifests default to **no new Jason Owner authority**, malformed manifests fail closed, and source-controlled `enabled` cannot be overridden by untrusted host environment. `infrastructure/jason-mcp/production-deploy.sh` and the native `tools/release_manager_host_runner.py` independently derive the same profile from reviewed candidate source. An attempt to simultaneously select the old V4 Entra-admin separation profile and the new Jason Owner policy is rejected. This changes no deployed setting until independently approved source merge and native exact-SHA promotion.

The new profile applies only to existing Jason Owner authorization entrypoints: exact capability grant/list/revoke, bounded canary readiness/observations, explicitly approved canary grant/revoke, bounded autonomous acceptance approval/status/run/revoke, Datto component standing approval decisions, and release Owner decision. It does not bypass independent authorization for each operation, target scope, per-action request and exact arguments, action approval, audit, provider permission, readback, immutable evidence, approval expiry, fail-closed idempotency or production freeze.

**Preserved boundaries:**
- Microsoft Entra/Office 365 administrative operations continue to require their separately authorized Microsoft admin provider permissions. Jason ownership does not impersonate or inherit the Microsoft admin's Entra roles.
- Provider writes execute through Jason's own governed provider/service identity, not the Owner's personal Microsoft account.
- No global allowlist widening, wildcard rights, migration of `person-al`, identity DB edits, or replacement of any existing Entra authentication.
- Production Ticket Core and Stage E unchanged. JSON playbook activation and legacy retirement require separate approval and are not implied by this change.
- Historical legacy and V4 admin-separated profiles remain for verified rollback only and must not be silently selected as the new Jason Owner profile.

## Verification and acceptance

Source tests cover: correct licensed Jason Owner allow/real idempotent exact-grant creation, Microsoft admin denial, wrong Entra tenant/object/principal denial, wrong assurance, missing bearer, wrong organization, client-scoped account, independent grant approval requirement, no duplicate grant or audit, source manifest fail-closed binding, native deploy/release source profile consistency, and historical release authorization regression. Source tests are NOT proof of production deployment.

**Release gate:** source/security review evidenced by the existing automated security and protected CI checks (no separate human security reviewer exists at AOT), immutable candidate commit SHA and scope digest, approved rollback SHA/plan, production freeze/release controls, Owner-approved exact native deployment, and MCP post-deployment readback from authenticated `al@teamaot.com`. Re-run the administrator-denial probes on the live service and validate original approval governance without using `al_admin@teamaot.com` as a Jason login. If any assertion fails, fail closed and invoke the separately approved exact rollback.

**Next objective:** once production Owner identity is actually accepted and required exact preproduction test targets and receipts are independently verified, run the per-playbook provider-connected parity/recovery matrix. Never run mutating tests against random customer devices or promote JSON versions on synthetic-test results.

## Human-review availability and no invented approvals

AOT has no independent human security reviewer. Protected CI, automated security checks, source/release-manager validation, immutable evidence, and the authenticated Owner exact-action approval are the applicable control paths. Do not invent an unavailable second person or represent a GitHub PR review as a mandatory separate human sign-off. An automated PASS is not an authenticated production release approval.
