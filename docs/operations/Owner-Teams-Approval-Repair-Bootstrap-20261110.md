# Governed Teams approval repair - exact bootstrap package (2026-11-10)

Status: SOURCE-ONLY PREPARATION. No active Owner approval, no Entra tenant write, no policy change, no production deployment. Tracking: PR #2395; issues #2376 and #1324.

## Required target behavior

- Licensed regular Teams recipient: al@teamaot.com; Entra OID bee80bdc-ffb0-4c50-b453-c09d4d411f5f.
- Separate privileged browser approver: al_admin@teamaot.com; Entra OID c848022d-e13b-4457-84b0-e2f5c00dcaf6. This account is intentionally NOT licensed for Teams.
- Microsoft tenant: f7054323-d52b-4863-8c2f-1898f0b6077c.
- Only the independently authenticated, MFA-verified privileged browser decision can approve the exact release. A Teams notice to the regular account is nonapproving.

## Verified live preflight

The existing delegated Microsoft Graph administrator session is authenticated to the exact tenant and has Application.ReadWrite.All and Policy.ReadWrite.ConditionalAccess. Permissions are NOT authorization to make high-risk changes without signed Teams governance. Forty-four app registrations were inspected; no application currently registers the intended V5 callback. The existing AOT_OpenClaw application has two credentials, and MUST NOT be reused or changed. The tenant reports zero authentication-context references and no CA policy targeting a context. Six enabled MFA policies explicitly exclude the admin; the seventh is role-targeted but does not enforce the V5 context. The external HTTPS health endpoint responds 200, which is NOT proof the new approval route is live.

Root installed approval policy is V4 admin_approver_separated. Production remains on last-known-good aa6fa38a29b803e11ada63afb3cf25d17b7daf44. Protected CCC, drift, and full-integrity health failed. The approval/bootstrap recovery must not clear or bypass those controls.

## Exact tenant change proposal - NOT YET AUTHORIZED

1. Create a new single-tenant confidential Web application named Jason Protected Release Approval. Register only the Web callback https://mcp-jason.teamaot.com/admin/release-approval/callback. OIDC scope must be openid profile; no Graph application-write scopes requested by this app, public-client authentication, implicit grant, or secrets in Git.
2. Create authentication context c1 named Jason protected release admin MFA through the versioned Microsoft Graph API. Re-read context inventory immediately before write and refuse to replace any previously created context.
3. Create an independent Conditional Access policy initially in report-only state. Conditions: only authentication context c1, browser client type, exactly privileged admin OID c848022d-e13b-4457-84b0-e2f5c00dcaf6, no groups/roles/other users, MFA grant required. Following separate exact Teams approval for enforcement, enable and independently verify the policy plus a fresh admin MFA sign-in.
4. Store new OAuth confidential credential and new Ed25519 signer private key in governed OpenBao, not a local plaintext or the repository. Versioned V5 policy may reference only separately verified app ID, enforced CA receipt hash, public signer fingerprint, exact tenant and Entra identity bindings, and HTTPS callback origin.
5. Prepare the full reconciled protected-main release with exact immutable candidate SHA, manifest and scope SHA256, known LKG rollback SHA, isolated preproduction, protected security/rollback CI and root compatibility. Do not treat the current draft PR HEAD as deployable.
6. Migrate installed V4-to-V5 ONLY after real one-time, exact-scope signed Owner authorization via an authenticated Teams process that can reach the regular account. Existing V4 admin Teams card cannot do this; no ordinary message, forwarding, chat approval, administrative sign-in or locally forged receipt is acceptable. If the authenticated bootstrap path is unavailable, escalate and do not change live policy.
7. After valid activation, send one regular-account Teams notice, witness actual visibility, separately complete the protected admin browser MFA/approval, verify immutable one-use signed decision and native root consumer, CCC, full-integrity PASS, freeze restoration, rollback, and two healthy independent postflight cycles.

## Required exact Teams authorizations

TENANT CONFIGURATION: named application, dedicated redirect, c1 auth context, exact admin OID, scoped CA MFA policy, report-only-to-enforced promotion, change/rollback manifest hash, no unrelated credentials or existing policies.

PRODUCTION BOOTSTRAP: final immutable release SHA, reviewed manifest and scope SHA256, rollback SHA, V4/V5 byte-precise root policy transition, independent CCC and rollback/readback, bounded one-time freeze exception, and human Owner Teams signed decision under the separately reviewed bootstrap procedure. This consent never grants standing release authority.

ROLLBACK: restore byte-identical V4 policy, prior runtime approval mode, and production freeze through the native transaction; independently review and reverse only newly created Entra objects if unused, without touching existing app credentials, Conditional Access policies, or immutable evidence.

No approval request has been issued by this document. No existing governance is weakened.
