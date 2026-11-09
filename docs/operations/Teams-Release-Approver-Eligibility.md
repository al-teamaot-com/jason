# Teams Release Approver Eligibility — governed correction

## Scope and identity boundary

The V4 `admin_approver_separated` release policy identifies two immutable Microsoft Entra principals. The administrative Entra object ID remains the **only** eligible privileged release approver. The ordinary, licensed requester Entra object ID is **not** an authorized release approver and receives only status notifications. No email, UPN, display name, mutable contact alias, or chat claim substitutes for a signed privileged identity.

The previous implementation validated that the privileged object ID was active but did not validate the **Teams entitlement needed to receive and act on a Teams approval**. Thus a provider-accepted message could be presented as a usable approval even when the admin identity could not sign into Teams.

## Corrected behavior

1. For V4 only, before persisting a newly actionable approval or a bounded renewal, the existing release maintenance worker verifies the configured administrator's **exact** tenant and Entra object ID against the active Microsoft identity binding.
2. The existing Microsoft Teams gateway uses its existing app-only Graph credentials to retrieve `/users/{id}?$select=id,accountEnabled,userType,assignedPlans`. Only an enabled, tenant-local member with the documented `TEAMS1` service-plan ID `57ff2da0-773e-42df-b2af-ffb7a2317929` and `capabilityStatus=Enabled` passes. An unlicensed account, disabled Teams plan, identity mismatch, Graph error, missing permission, or unexpected response **fails closed**. This deliberately does not add Microsoft Graph permissions or change any account licensing. Some newer Teams service plans may require separate reviewed identifier support; an unrecognized plan fails closed.
3. The gateway performs the same licensing check when actually sending release approval Adaptive Cards. An ordinary text notification does not become an approval card.
4. If V4 admin eligibility fails, the maintenance worker creates **no new pending actionable request** and records a mode-0600 bounded per-release diagnostic. If an older release already has an unused pending request, it is not reissued, rebound, approved, or revoked automatically; its original signed identity binding remains intact, and a blocked diagnostic is recorded. The existing TTL/expiration lifecycle remains.
5. On first blocked observation only, the requester may receive one **informational text-only Teams message** through the existing gateway, addressed to the separately persisted regular-requester tenant + Entra object ID. It contains **no Adaptive Card or approval action**. The original administrative role is not transferred.
6. Any corrected privileged approval authority, alternate licensed administrative Teams identity, or approved stronger step-up mechanism is a **separate governed Owner policy decision** requiring exact scope, identity verification, CI and signed Teams release authorization. The repair does not invent one.

## Tests and acceptance

Simulated tests cover correct tenant/admin, unlicensed admin, wrong actor, disabled account, Teams entitlement suspended, Graph permission failure, malformed assigned plans, historical pending requests, immutable blocked audit, single informational notice, wrong recipient and no authority transfer. Both existing Teams gateway and release approval suites must remain green.

Microsoft Graph note: the app-only gateway cannot use delegated-only license-detail APIs. The implementation uses the existing user's `assignedPlans` property instead of `licenseDetails`.

## Release state and verification

This correction is source-only pending governed CI/source integration. It does **not** modify the production recipient bindings, existing signed approval record, privileged release policy, PMV3 integration gate, engineering Owner pause or production freeze. Activation requires a separate source-approved release and post-deployment verification of an unlicensed admin's blocked status and an eligible privileged recipient's signed callback.

The unlicensed `al_admin@teamaot.com` account cannot execute Teams approvals today. The fix makes that reality explicit rather than misleadingly claiming an actionable approval card exists.
