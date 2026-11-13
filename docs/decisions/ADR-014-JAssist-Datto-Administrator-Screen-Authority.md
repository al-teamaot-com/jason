# ADR-014 — J-Assist Datto Administrator Screen Authority

**Status:** Owner accepted on 2026-11-06; preproduction policy implemented, live source verification incomplete
**Decision owner:** AOT Owner
**Scope:** J-Assist technician-initiated screenshot assistance only
**Affected providers:** Datto RMM, Microsoft Entra, Jason governed session/evidence service
**Production status:** No deployment, no enabled Send-to-Jason control

## Context

The initial J-Assist design required the server to prove that the individual signed-in Datto technician's currently **active** security level grants Web Remote and, if relevant, Web Remote PowerShell rights for each requested device. Datto permits multiple assigned security levels with just one active at a time. That requirement would demand a live active-session level resolver that is not established for Jason.

AOT's Owner explicitly chose Datto RMM's **built-in Administrator security level** as the initial J-Assist access gate. This is Datto-native membership, **not** membership in an Entra group, KaseyaOne group, or a custom role named Administrators. The level is static and immutable and provides full Datto functionality and visibility of all devices in the Datto account.

## Decision

For J-Assist **screen-assistance intake only**, an authorized AOT technician is eligible when the **same individual** has a current, verified **assignment to the built-in Datto RMM Administrator security level**, even if the user's active Datto UI security level currently differs. This is an intentional Jason policy decision and **does not assert native Web Remote session permissions**.

The admission rule is:

1. Independently authenticate the technician with AOT Entra and validate a signed access token for only the registered J-Assist SPA client and `JAssist.Send` delegated scope.
2. Bind the authenticated Entra object identity to exactly one **enabled** individual Datto RMM user in the AOT Datto account using a server-owned authoritative mapping; a matching email address alone is insufficient.
3. Obtain fresh **Datto-origin** proof of the built-in `Administrator` security-level assignment for that user (not the user's API-key security level). Maximum evidence age: 30 seconds, including revocation rechecks.
4. Independently verify the requested Datto device UID belongs to the pinned AOT account, and bind the recipient session to that device, user, account, nonce and expiry.
5. Require explicit technician screenshot initiation, content policy/DLP pass, a verified transfer receipt, short retention and an audit trail.
6. Fail closed if any provider or identity dependency is missing, stale, ambiguous, or reports revocation.

**No new execution rights.** Native Web Remote PowerShell, component dispatch, service changes, restarts, reboots, ticket changes, shell access and other actions remain subject to their independently governed capability/technician approval boundaries. This policy is never used to authorize them.

## Provider-backed source limitation

Official Datto RMM documentation provides a read-only `GET /v2/account/users` API for identity/user records; the published user response does not establish assigned security-level membership. Datto's native **Setup > Users** interface does expose an `Administrator` field and **Security Levels** column that can be included in a CSV export. That UI/export may help with a controlled, witnessed pilot inventory, but a saved CSV alone does not meet the 30-second live membership and revocation requirement for automated admissions.

Do not create an unsupported Datto API endpoint, automate an undocumented browser authorization cookie, trust the shared API key's security level, or infer membership from the Chrome extension, Entra identity, tab URL, display name, or a stale roster. Verify the accepted Datto membership source and its user-ID binding before activating the feature.

References (Datto RMM):
- https://rmm.datto.com/help/en/Content/3NEWUI/Setup/SecurityLevels.htm
- https://rmm.datto.com/help/en/Content/3NEWUI/Setup/Users.htm
- https://rmm.datto.com/help/en/Content/3NEWUI/ColumnChooserFieldDefinitions.htm
- https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm

## Implementation and proof

- Existing preproduction contract: `experiments/j-assist-bridge/datto_administrator_authority.py`
- Regression suite: `experiments/j-assist-bridge/tests/test_datto_administrator_authority.py`
- The class admits `screen_assistance` only, requires `Administrator` assignment, enabled verified user, proof <=30 seconds, pinned account, and account-owned device UID.
- The production J-Assist Send button remains disabled until the provider-owned proof adapter, protected image ingress, DLP, audited evidence storage, ChatGPT retrieval and complete acceptance are verified.
- Source may be reviewed, tested and prepared for release under standing engineering authority. Deployment is frozen absent separately authenticated, exact-revision release authorization under the Project Jason Governance Handbook.

## Rejected alternatives

- **Require the active Administrator level** — rejected for J-Assist screen-intake eligibility only; the Owner specifically selected assigned built-in membership. Still required for actions only where native Datto policy dictates it.
- **Grant all AOT Entra users or an Entra Administrators group** — rejected; Entra sign-in alone does not demonstrate Datto RMM membership.
- **Treat API key's security level as technician's** — rejected; Datto documents them as independent.
- **Trust an uploaded CSV permanently** — rejected; lacks live revocation and source freshness.
- **Enable Send without proof** — rejected; fail-closed by default.
