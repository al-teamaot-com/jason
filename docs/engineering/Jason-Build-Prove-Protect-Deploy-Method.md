# Project Jason — Build → Prove → Protect → Deploy

**Status:** Owner-approved engineering practice (2026-10-22); documentation proposed for normal protected GitHub review.  
**Authority:** Subordinate to Jason's Constitution, identity/tenant controls, approved development authority, J-CHANGE-001/002, protected CI, and governed Production/Release Manager.  
**Applies to:** New Jason capabilities, integrations, workflow modifications, and defect repairs; first to Universal Teams Approvals, then PO/invoice intake, then QuickBooks bank and credit-card reconciliation.

## Purpose

Prove basic functionality before introducing nonessential workflow complexity. Previously Jason often mixed basic integration defects, approvals, production hardening, and deployment failures, making the first broken boundary impossible to identify. This method isolates those questions and requires a repeatable test at every stage.

**Build → Prove → Protect → Deploy is a development sequence, not an authorization waiver.**

## Nonnegotiable safety from the first experiment

- Use an isolated dev/test environment with synthetic records and mock providers for minimally restricted experiments. Never exercise deliberately relaxed controls against real client data, real money, production machines, or live provider writes.
- Preserve secrets, environment isolation, applicable tenant boundaries, and controlled network access. Clearly label simulated identities and inputs. A mock/simulation is never evidence of real Entra authentication or real provider authorization.
- Never disable or bypass protected source, immutable release selection, root-owned controller, CCC, audit, constitutional controls, or existing production access policies. No unmanaged production writes or direct-provider bypass.
- All tests with actual Teams staff or actual third-party providers require the established identity, scope and permission controls from the start. Changes to sensitive live systems remain separately authorized.
- Feature flags for intentionally simplified tests must be test-only and refuse production operation; no generalized `allow_all`, real customer bypass or elevated service credentials.
- Inventory the full intended set of API scopes, Teams app installation permissions, identity mapping, callback rights, human approval categories and durable data storage **at the beginning**, not six weeks after proving the prototype.

## 1. BUILD: simplest functional behavior

1. Name one real-world user outcome and create a deterministic input/output fixture.
2. Reuse existing canonical interfaces and components; avoid new managers, bots, ledgers and bypass paths.
3. Prove the smallest happy path in a controlled simulated environment with observable correlation and error output.
4. Stop and fix the first failing functional layer. Do not bury an interface/transport fault under yet more approval policies.
5. For a workflow that will use Adaptive Cards, design the card interaction/response shape from the outset; **Adaptive Cards are the preferred presentation for actionable Teams requests**, with text fallback only for a proved unsupported/unavailable card surface. Text fallback does not authorize sensitive operations.

**Exit:** The minimal fixture reproduces success and has a stable test.

## 2. PROVE: real harmless integration

1. Exercise the real transport and provider using a bounded, approved, **nonexecuting** test or harmless read, with the original security floor still enabled.
2. Test at least one ordinary AOT user besides the Owner where role/identity matters, including a first-time app/conversation enrollment where applicable.
3. Record provider-accepted vs actual message identity in Teams vs card rendered/seen vs authenticated response. Never infer one state from another.
4. Verify at least one negative/failure path. Preserve exact evidence of the first boundary that fails and add a durable regression case.
5. Raise actual external requirements immediately: *who must grant which exact scope, what it permits, why it is needed, and the safe action*. No silent days-long dependency loops.

**Exit:** A verifiable real integration succeeds safely; missing permissions are explicitly recorded rather than hidden by production rollout.

## 3. PROTECT: incremental hardening with continuous regression

Apply the existing required protections in a deliberate order to the already-proven path: requester/recipient binding, tenant/client isolation, data-release policy, capability authority, bounded immutable plan, qualified approver routing, signed callback and one-time decision, replay/expiry/denial, idempotent execution, audit, failure escalation, and durable recovery. **After each protective layer, rerun both the original success case and its relevant negative tests.** If a control stops legitimate work, diagnose the policy decision and adjust its justified scope through normal governance, not by bypassing the control.

Keep transport permission distinct from end-user approval and read-only access distinct from data disclosure. No workflow may silently acquire new permissions or perform financial/disruptive operations merely because the prototype was successful.

**Exit:** The original operation still works correctly; unauthorized users, actions, scopes and replays fail closed. Evidence is linked to the exact tested revision.

## 4. DEPLOY: governed release and real acceptance

Reconcile source against protected main; pass required CI, overlap, risk and policy checks; obtain the exact bounded human approval if needed; promote only through the canonical controlled release; verify runtime, gateway, controller, policy/feature flag and rollback health. **Production acceptance is a real AOT workflow completed end-to-end** with independent provider evidence and correct disclosure/authorization. A merged PR, green test job, successful health ping or offered Teams card alone is not completion.

If deployment cannot proceed because of an actual protected approval, missing Graph consent, privileged step or external dependency, notify the proper human **immediately** through an already authorized route, with the specific required action, rather than leaving work stuck.

## First acceptance track — Teams Universal Approvals

Use the existing Teams gateway, shared Teams Communications, Universal Interaction, persisted ApprovalRequest service, signed dispatcher, and guarded Central Orchestrator. Do **not** create a second bot or approval database.

1. **BUILD:** Render one canonical Adaptive Card and process Approve/Deny in test-only mode without side effects.
2. **PROVE:** Show a real benign card to a named authorized AOT requester/approver and confirm both a separate Approve and Deny in Teams (correct actor, real callback, audit, no execution). Verify a first-time non-owner Teams recipient and honest transport receipts. Distinguish text/card extra messages; no blind resends.
3. **PROTECT:** Validate incorrect approver, disabled/stale user, cross-tenant, expiry/replay/duplicate buttons, threshold/delegation, provider timeout, delivery-unknown, restart and durable escalation. A synthetic `accepted:...` reference must never be reported as verified human delivery. Owner escalation between **04:00–17:00 America/New_York**; outside that window notify for morning but require no response until available.
4. **DEPLOY:** Existing exact-SHA approved, independently tested production release, with a real all-staff approval and rejection, post-action verification and recovery, before asserting 100% expected-function coverage.

Next reuse the same service for actual PO/invoice staff submissions and later QuickBooks reconciliation authorizations. Business-specific finance and disruption safeguards are not replaced by the common card.

## Evidence and learning requirements

Every meaningful failure yields one recorded first failed boundary, actual root cause rather than symptom, a bounded fix, a regression reproducing the original failure, and post-fix proof. A recurrence should correlate to the existing incident—not create another stalled issue. Status must distinguish **working**, **not working**, and **needs a human action**, and never claim delivery or production success without verifying it.

This method does not introduce another engineering queue, production manager, release lane or project. Reuse the existing owner-approved development workflow and related P0 issues (#1440/#1545, #759, #1467/#1470, #635).