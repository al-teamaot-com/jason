# AOT Jason: regular requester versus privileged administrator (V4)

**Classification:** HIGH RISK - identity, authorization and production release controls. Tracking: issues #2104 (requester/approver separation) and #2365 (XYZ notification).
**Deployment:** Source development only. Do not merge/deploy without independent high-risk review and exact-SHA release authority.

## Verified separate Entra identities

- **Regular requester/technician:** mail al@teamaot.com, actual Entra UPN Al@teamaom.com, Entra object bee80bdc-ffb0-4c50-b453-c09d4d411f5f.
- **Privileged administrator/approver:** UPN al_admin@teamaot.com, Entra object c848022d-e13b-4457-84b0-e2f5c00dcaf6.
- Both belong to tenant f7054323-d52b-4863-8c2f-1898f0b6077c, both enabled, and both retain different canonical Jason person-entra-{OID-without-dashes} identities. Never conflate the two accounts or use email/UPN strings as authority.
- The legacy Owner role name person-al remains a release/CCC policy role identifier only. It does not become the everyday logged-in identity or an implicit right to operate provider tools.

## Strict versioned policy

The reviewed source config/mobile-release-approval-policy.json declares V4 with policy_mode admin_approver_separated and two exact immutable Entra tenant/object pairs. Existing signed-Teams challenge, exact-SHA/manifest/TTL, independent CCC, preproduction, one-transaction unfreeze, freeze restoration and rollback gates remain mandatory.

Runtime source profile JASON_RELEASE_MOBILE_APPROVAL_MODE=admin_approver_separated and MCP source profile JASON_AOT_ADMIN_APPROVER_PROFILE=admin-separated-v1 derive from the same validated source policy and are separately opt-in. The root-owned production 0600 policy is distinct; V2/V3 deployments cannot silently enable V4 and V4 may not accept old policy. Host release manager, runtime/MCP deployment scripts and runtime validator must agree. Fail on unknown/mismatched source, profile, role pair, tenant, object, or insecure file. No manual identity SQLite edits.

For release Teams cards, the sender resolves the admin exact tenant/object binding. No fallback to regular-user email for V4. The signed callback must independently verify that same admin object, an active unscoped AOT human identity, original issued challenge, unchanged immutable release and policy, pending status and TTL. Personal-user, cross-tenant, stale/replayed, disabled and client-scoped attempts fail closed. Original signed Teams evidence retains the true Entra identity; person-al is merely the host authorization role label.

The existing MCP exact-grant administration endpoints are admin-only under V4 and require the original authenticated Microsoft OAuth tenant/object, matching existing provisional Jason identity and unscoped AOT principal. The regular user must not administer grants. Any resulting grant still requires exact capability, active subject, correct company, execution approval, audit and any native provider checks. No wildcard, blanket administrator, unapproved execution or standing cross-tenant access.

In V4 the privileged admin principal does NOT automatically inherit the organization-wide routine human Autotask ticket-write grant. The separate regular authenticated technician retains existing eligible AOT human read and routine approval-required write policy; native Autotask resource permissions, idempotency, non-disruptive limits, approvals and readback remain unchanged. A privileged admin only performs a normal provider operation under a separately approved exact grant, not by virtue of its approval role.

## Protected rollout and migration

1. Independently verify current Entra evidence, exact account and tenant/object pairing and existing live bindings; preserve immutable references. No identity binding migration is needed.
2. Run focused new V4 negative cases, original V2/V3 regression, native host release and deployment contract tests, protected CI and independent security review.
3. Integrate through a separately authorized PMv3 release-recovery path if the protected main remains locked. Build exact-main immutable candidate, full scope SHA and rollback SHA. Run provider-mutation-disabled preproduction and verified rollback readiness.
4. **Critical bootstrapping:** Current V2 release approval route historically maps person-al to the REGULAR account. Do not present that regular-account click as a new privileged admin approval under the Owner clarification. Obtain separately authenticated, exact-scope administrator transition approval through an existing governed high-risk change control. If native release does not offer a valid bootstrap path for V2-to-V4, record the exact missing gate and engineer a security-reviewed transition. Never forge approval, edit identity database, loosen the original freeze, or bypass host controls.
5. Only after valid release gates and exact-SHA Owner authorization, perform a single native PM promotion, verify runtime/MCP/host alignment, live admin vs regular signed identity denial tests, and rollback/postflight. Restore production freeze byte-for-byte; retain engineering pause and automatic-promotion hold.
6. An admin account does not silently gain regular technician rights on production, and the regular user must be denied privileged approval cards.

## Controlled XYZ acceptance after V4 is LIVE

- NORMAL account requests an authorized exact notification on XYZ Test Company 1158, ticket T20260926.0088 (ID 141431), contact 30683022, recipient al.bccomputers@gmail.com, workflow xyz_client_notification_acceptance, template xyz-controlled-client-notification-acceptance-v1.
- ADMIN account separately grants that regular identity only service.ticket.client.notification.create, company 1158, EXECUTE with mandatory exact-action approval. Record grant ID and audit, no general privilege elevation.
- Carry out at most ONE governed, approved provider send. Record pre-send NotificationHistory and exact action/plan fingerprint. Independently read new provider notification recipient, template, company and ticket; verify actual test mailbox receipt separately. Unknown provider outcome means no blind resend.
- Check wrong-client/recipient/identity and replay denial before provider execution, ticket unchanged, no duplicates; revoke temporary grant and read back revocation.
- No unrelated Gromelski policy changes or endpoint actions. Source tests are not provider acceptance; do not assert delivery before an actual receipt.

## Scope boundary

This change activates account-role separation only after a separately approved release; it is NOT production authorization. Approval for privileged actions beyond the existing release/CCC and exact-grant admin surfaces continues to be controlled by the other registered approval policies, which need separate review before asserting all operations use the new admin. The original ticket-notification acceptance remains incomplete until a real authorized single-send and independent readback.

## Reviewed parallel source overlap (protected integration gate)

This change was created from protected main c43e88e072c0b35c5b342d5e712fe34565b3e0cd. Parallel open PR work overlaps the exact paths below and must be independently reconciled in the approved PMv3 integration window. It is NOT included or implicitly authorized by this candidate:

- #2355: both native runtime and MCP deployment scripts (staff-note rollback authority).
- #2343, #2333, #2305, #2304: MCP server dispatch for procurement, endpoint assessment and Datto diagnostics/job output.
- #2336, #2282, #2177: runtime composition for financial statements, KFS/SharePoint.
- #2279: host Release Manager (superseded signed Teams card lifecycle).
- #2269: Teams mobile-release approval lifecycle and CCC communications.

The release gate must inventory current main, inspect any changed overlap against the merged candidate, regenerate full scope and candidate SHA after integration, and rerun protected tests. Do not silently merge, rebase, discard, or deploy any of these parallel PRs to make the identity feature pass. Existing Owner freeze and release lock remain authoritative.
