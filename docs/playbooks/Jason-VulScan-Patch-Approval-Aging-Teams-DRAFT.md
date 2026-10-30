# VulScan Patch Approval Aging and Canonical Teams Notification — Preproduction Design

**Status:** Design in isolated feature branch; not promoted, merged, or deployed.
**Owner:** AOT IT Operations
**Parent playbook:** `vulscan_missing_patch`
**Proposed rule ID:** `vulscan_patch_approval_aging`
**Proposed version:** `0.1.0-draft`

## 1. Section Goal
Identify vendor-released Windows patches that remain NOT_APPROVED after AOT's intentional 15-calendar-day review delay, notify AOT's owner through the **existing canonical Teams communication service**, and escalate only after a bounded grace period. Preserve the original VulScan diagnostic/patch/remediation workflow and human approval authority.

Success requires release-date evidence, deduplicated patch-level notifications, an official Microsoft knowledge-base URL and sourced short description where available, correct owner delivery through the canonical transport, and no patch/ticket mutation caused by the notification.

## 2. Trigger
Apply to a governed, exact-KB Windows patch observation from VulScan/Datto RMM with authoritative status `NOT_APPROVED`. Aggregate same-KB observations across tickets/devices using verified per-client bindings. Do not start a separate per-ticket notifier.

## 3. Scope and Boundaries
Notification and monitoring only; this rule does **not** approve, install, decline, suppress, reboot, change patch policy, or modify tickets. No direct provider, Teams bot, transport, OAuth registration, queue, or approval ledger is created. Keep Central Orchestrator, exact requester grants, tenant/client isolation, `direct_provider_access=false`, and approved communication audience controls.

## 4. Initial Identification
Confirm canonical Microsoft KB identity, release date, edition/update applicability, affected devices and companies, current patch approval state, and any already recorded intentional defer/decline decision. Do not merge different revisions/releases or patch identities solely because KB display text matches. Reject mismatched or cross-client joins.

## 5. Expected State
A patch is either approved, intentionally deferred/declined under documented technician authority, superseded, or pending review within AOT's ordinary 15-day window. Unapproved patches beyond the window produce one actionable owner notification, not one message per endpoint.

## 6. Persisted State Model
`observed -> awaiting_age -> eligible -> notification_pending -> notification_accepted -> notification_verified | delivery_retry -> acknowledged | deferred | approved | superseded | escalation_due -> completed`

Persist KB/patch identity, authoritative release timestamp + source, applicability set and snapshot fingerprint, first-observed timestamp, approval status, documented exception, recipient identity binding, template/version fingerprint, day-16 and day-21 event keys, attempts, Teams correlation/provider message IDs and delivery evidence, next retry, and event disposition. Transport accepted is not user-delivered.

## 7. Diagnostic and Source Workflow
1. Read exact approval state from Datto RMM and active same-company affected endpoints.
2. Resolve vendor publication date and summary from authoritative Microsoft support/update sources, recording URL, observed timestamp, publication date, and update applicability. Use *release date*, not first VulScan detection or ticket creation, for aging.
3. Apply calendar-day arithmetic using explicit timezone and UTC timestamps; a full 15-day delay ends before the day-16 first notice. Define the day boundary in AOT local timezone (`America/New_York`) and test DST crossings.
4. Validate the exact official HTTPS support.microsoft.com/help/<KB> link or other canonical Microsoft KB article URL by fetching it. Do not fabricate a link, known-issue assertion, or description. If no trustworthy summary is available, mark `Microsoft description unavailable`; if no verified link, omit the action and mark `Microsoft KB link not verified`.
5. Build a concise description from the verified KB content only, including notable security fixes/known issues when clearly documented; no invented CVEs.
6. Count verified affected clients/devices at the time of sending; preserve scoped identifiers in the owner-only message. Any missing or partial coverage must be labeled, not silently treated as a complete count.

### Datto RMM manual approval / deferral authority (Owner decision: October 30, 2026)

**Section Goal:** Reuse the technician's existing Datto RMM Patch Management decisions as the *only* operational source of deliberate patch holds. Do **not** create a separate approval ledger. Prove the exact identity, decision and freshness before suppressing an owner reminder.

Datto RMM applies automatic Patch Management policy filters, a separately maintained **Manual approval** list (Available / Approved / Not approved), and an individual **device-level** override. These are not equivalent. A normal `installStatus=NOT_APPROVED` or `manualOverride=false` is not evidence that a technician intentionally deferred or declined the KB. A positive, current `manualOverride=true` with effective `NOT_APPROVED` indicates a device-level explicit hold; the source-only adapter conservatively classifies it as `declined` (not time-limited `deferred` and **not proof of Owner identity or approval date**). A manually denied KB in the policy's verified Manual approval list is also `declined`; absent an explicit denial, `review_pending` requires independently verified completeness across **the entire manual approval table for the exact assigned policy**, with a current read and no conflicting device-level override. Automatic filters and the age-based Windows Update deferral window never count as human decisions.

**Provider-backed source contract:** New `DattoRmmPatchReviewReader` uses only Jason's existing governed `endpoint.patch.search` for an exact, same-site KB/device; the separate injected `VerifiedDattoPolicyManualReview` must come from an independently authorized Datto Patch Management policy read showing the complete Manual approval state. Both are checked for full pagination, exact client/site/device/policy/KB scope, source reference, timestamp (15-minute maximum), and status consistency. Missing/partial/unknown/manual flag of the wrong type, cross-client reuse, stale metadata, multiple KB matches, or a policy table that cannot attest a negative **fails closed**. The pre-send Teams outbox re-reads the Datto decision; a newly denied update cancels an already queued reminder.

**Deployment dependency:** Datto's 15.2 release notes introduce `GET /v2/device/{deviceUid}/policies/patch-management` with approval rules, schedule, scope and pagination. Whether that response includes a reliable *complete manual approval list* must be established against the actual tenant/provider response before a live reader can be enabled. The vendor's deployment calendar is staggered: its stated US East Concord target was November 5, 2026 and Vidal November 9, after this checkpoint; the tenant's Datto platform and API readiness must be confirmed, not assumed. No direct Datto API credentials, new permissions, patch writes or notifications are authorized by this design.

**Acceptance:** Test a controlled manually denied KB and a non-manually-denied KB under the exact same site/policy, plus one device-level override; verify source completeness and alternate-policy isolation. Prove that missing evidence never creates or sends a notification, that V1 ten-day ticket handoff is unaffected, and that all Datto/Teams calls use existing governed services. Until live provider-backed evidence and exact-SHA Production Manager acceptance pass, **draft / disabled / no production release**.

## 8. Decision Gates
- Days 0–15 from vendor release: observe only.
- Day 16: if still NOT_APPROVED and no approved deferral/decline/supersedence, one owner notice.
- Day 21: if unchanged, still unapproved, and no recorded decision, one owner escalation notice.
- Suppress notices once approved, superseded, or intentionally deferred/declined, but retain audit history and the next scheduled policy review of any intentional deferral.
- Exception: urgent out-of-band security response requires a separately approved policy; this ordinary-aging rule cannot redefine emergency patch handling.
- For unknown release date, do not manufacture age or send a falsely time-qualified notice. Record an evidence gap for technical review.

## 9. Remediation / Communication
Send only through `JasonTeamsCommunicationService` / existing governed communication.teams message capability and preexisting Teams gateway adapter, after live owner identity binding and audience-policy verification. Render a bounded versioned card/message using source-backed fields:
- Title: `Jason — Patch Approval Review` or `Jason — Patch Approval Escalation`.
- KB, exact update title and verified vendor release date.
- Age in calendar days, approval state, affected client/device counts.
- Brief sourced description, known issues only when verified.
- Official verified Microsoft KB link, if available.
- Action required: review/approve or explicitly defer, following pre-existing technician process.
- No actionable Approve button unless a separate governed, persisted approval workflow is explicitly approved. A message/link does not grant authority.

## 10. Retry Policy
Use the existing shared Teams delivery retry, provider-receipt and reconciliation contract; bounded exponential retry, replay/idempotency, TTL, and dedupe. Never send historical flood after outage. Do not claim delivered from gateway acceptance alone.

## 11. Recheck
Daily patch eligibility evaluation; durable scheduler state survives worker restart. Suppress duplicate day-16/day-21 notifications by stable patch/event/recipient key. A changed impact count by itself should not spam the owner; material severity/identity change may require a separately defined policy.

## 12. Aging / Stale Condition
This policy *replaces the conflicting ten-day NOT_APPROVED human-review aging for the same patch approval decision* when adopted: the 15-day AOT release review period plus day-16 notification and day-21 escalation governs approval oversight. Do not silently modify other ticket SLA clocks, repair retries, or already persisted decisions. Reconcile existing ticket-state schedules and migration before activation.

## 13. Dependencies
Governed patch status, authenticated client/device mapping, vendor KB metadata verification, active owner identity binding, canonical Teams sender/audience engine, durable notification ledger and scheduler. Missing dependency becomes a bounded evidence/delivery blocker without direct provider workaround.

## 14. Documentation
Persist source citations/URLs, release date used, patch identity, affected scope, policy/exception decision, message rendering fingerprint, attempts, provider receipt, and final verified delivery/failed/unverified result. Do not emit duplicate Autotask notes solely for unchanged daily checks.

## 15. Failure Handling
Fail closed for uncertain identity, release date, unauthorized recipient, missing binding, invalid URL, unknown patch approval status, or unsupported transport. A missing Microsoft article description/link may degrade message content while preserving truthful labels; it must not turn an unverifiable release date into a time-based notice.

## 16. Escalation
Day 21 owner follow-up; technical exception if missing sources or bounded delivery retries exhaust. No automatic patch approval or unexpected Help Desk ticket reassignment by this notification-only rule.

## 17. Verification
Verify exact patch status and age at send time, versioned card content, source URL, dedupe key, active Teams identity, actual provider-backed receipt and ideally human-visible arrival. Acceptance must distinguish `submitted`, `accepted`, `delivered/verified`, and `decision recorded`.

## 18. Completion
The notification workflow closes when approval, documented intentional deferral/decline, supersedence, or a durable monitored escalation is verified. A notification is not evidence that the underlying vulnerability is resolved.

## 19. Final Record
Record KB, release date, age, decision state, recipient binding reference (no secrets), source URL, delivery verification, last event timestamp, and next owner action.

## 20. Required Capabilities
Existing governed DRMM exact patch read; Autotask/CI/device mapping reads; approved Microsoft documentation retrieval; canonical Teams communication/audience policy; persisted scheduler and dedupe; approved owner identity resolution. Do not add another raw Teams transport or approval callback.

## 21. Controlled Acceptance
Test release days 14/15/16/20/21 and DST boundary; missing date; false/superseded/approved/declined states; two clients with many devices produce one event; cross-client isolation; duplicate tickets; restart/replay; verified/unverified Microsoft URLs; source-backed descriptions; owner binding missing/revoked/wrong tenant; Teams transport transient failure and stale-message TTL; verified provider receipt vs human arrival; no production patch/ticket updates. Verify the unchanged behavior of invoice/PO, release-management, playbook, and generic Teams notifications.

## 22. Section Goal Closure
Remain **not complete** until implementation, tests, protected CI, security/constitutional review, exact change inventory, preproduction acceptance, and Owner-approved production release prove this rule. Update support/roadmap and Grafana evidence only when justified.

## 23. Autonomous Eligibility
No new standing authority. Any future unattended notification requires exact owner-reviewed promotion of rule version, intended recipient, send capability, and immutable source fingerprint. Material updates require renewed review.

## Implementation notes / open engineering checks
- Inspect current canonical Teams service, shared sender and October 29 owner-identity fix before implementation.
- Confirm approved provider/API source for authoritative vendor release timestamp and KB support article text; do not assume a web search result is a trusted feed.
- Decide whether day-21 escalation is a second Teams message only (recommended) or also changes ticket ownership (not authorized by this draft).
- Check any active ten-day NOT_APPROVED waiter migration against the original patch workflow.
- **Do not merge, promote, deploy, or activate** from this draft.


## V2 refinement decisions (2026-10-30)
1. **Vendor release versus revision:** use the authoritative security update release date; record later revisions separately and do not reset the waiting clock merely because KB metadata changes. A genuinely new superseding update receives its own policy decision and documented release-date basis.
2. **Per-policy applicability:** group by exact patch + Datto patch policy, and resolve client/site/device applicability independently. Never infer that global approval implies every policy is approved.
3. **Separate Teams reminder from ticket handoff:** Day 21 is an owner Teams escalation, **not** automatic reassignment of individual tickets. Reconcile the existing 10-day NOT_APPROVED ticket handoff before any runtime activation.
4. **Actively exploited exception:** independently verified exploited-in-the-wild/high-priority emergency criteria can trigger immediate review; they grant no automatic approval or remediation authority.
5. **Known issues / supersedence:** source all summaries, applicability and known issues from authoritative Microsoft documentation. Record article retrieval timestamp and source. Unknown must remain unknown.
6. **Acknowledgment and deferral:** use existing governed, signed interaction/approval machinery *only after* separate exact workflow review. Until then accept read-only monitoring of decisions recorded through existing approved technician processes. A notification or card click alone never changes patch policy.

## Implementation boundary
A first deterministic implementation exists in `implementation/runtime_service/src/jason_runtime/vulscan_patch_approval_aging.py` with unit tests. It produces **notification intent only**. It does not gather authoritative release data, write scheduler state, invoke canonical Teams transport, handle acknowledgments or change Autotask. No rule is deployed or autonomously promoted. The remaining integration work and provider-backed acceptance are mandatory before this draft can be considered operational.


## Preproduction implementation checkpoint — source branch only (2026-10-30)

The V2 modules added on this isolated branch are:
- vulscan_patch_approval_aging.py: deterministic per-policy and per-device decision evidence.
- vulscan_microsoft_release_evidence.py: validates release-health/KB provenance, exact KB matching, original availability date versus later article revisions, and verified article details.
- vulscan_patch_approval_notification.py: one owner message per KB/event; trusted Microsoft KB URLs, concise sourced summary and known issues, bounded presentation, fresh AOT-local snapshot gate; calls JasonTeamsCommunicationService instead of HTTP.
- vulscan_patch_approval_outbox.py: bounded at-most-once sender drain with an independent authoritative state recheck, provider receipt retained as unverified until human evidence is available.
- Existing SQLiteOperationalWorkStore outbox now accommodates patch-level events with a documented ticket_id=0 aggregation sentinel. The ordinary ticket notifier excludes them, preventing accidental legacy message delivery.
- Tests cover the decision, metadata, sender, safety, durable store and negative cases.

**Provider evidence contract:** Microsoft evidence must be read through an approved governed reader. The Windows release-history/release-health page can establish the exact KB's initial availability date and OS applicability; the exact Microsoft Support KB article provides description and known-issues status. The Microsoft Security Update Guide/API can contribute security context and independent exploitation evidence, but its monthly CVRF document date is not automatically a particular KB's original release date. Sources may be unavailable; never invent facts or link destinations. Do not use a search snippet alone as an authoritative governed provider record. Relevant official source families:
- https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information
- https://www.microsoft.com/en-us/msrc/faqs-security-update-guide
- https://support.microsoft.com/ (exact verified KB article only)

**Boundary still to implement before promotion:** Running governed release-health/article reads, current cross-client patch-policy collection, owner-promotion-based runtime composition registration, and verified migration superseding the legacy ten-day ticket-aging handoff. V1 remains unchanged until V2 passes end-to-end acceptance. No feature activation by environment flag alone.

**Production preparation:** Protected CI, isolated preproduction source acceptance, existing Teams/invoice/PO regression tests, exact revision inventory and overlap reconciliation, proof of owner identity binding and canonical communication authority, no new credential or OAuth grant, release manager's LKG/rollback. Production pilot: stage disabled, then Owner explicitly approves exact SHA and one controlled provider-backed Teams test. Do not treat provider acceptance as human delivery.


## Additional preproduction source coverage (2026-10-30)
- **Governed patch collector:** `vulscan_governed_patch_source.py` requires preverified same-client CI/Datto UID and policy identity, performs exact `endpoint.device.read` and `endpoint.patch.search` through injected governed reads, and refuses ambiguous/mismatched KBs, devices, policy identity, or missing release metadata. An ordinary ticket is NOT automatically proof of a full client/policy inventory.
- **Dormant workflow composition:** `vulscan_v2_preproduction_workflow.py` combines a trusted complete target inventory, injected governed endpoint reads, source-verified Microsoft metadata, and existing canonical outbox intent. Shadow evaluation performs reads only; enqueue requires a separately supplied exact activation/owner authority verifier. The `VulscanV2ShadowMaintenance` cadence does not self-register or send.
- **Source integrity just before sending:** re-evaluation must match KB, original release date, active policy IDs, client/device counts, and the exact Microsoft-derived message body; if anything changes, the stale event expires. Crash/interrupted sends become delivery-unverified rather than being replayed.
- **Canonical Teams integration test:** the existing `JasonTeamsCommunicationService` is exercised in preproduction with mock transport and real audience/recipient policy checks; no customer message or live Teams POST occurs.
- **Outbox restart handling:** a claimed send that cannot be reconciled after five minutes is marked `unverified`, not automatically resent. Operator review is required before any manual resend.

**Important acceptance distinction:** These source integrations are wired through injected/fixture-backed governed read ports but NOT yet to an approved, running automatic source of complete Datto patch-policy inventory and Microsoft release-health/KB content. A Boolean proof flag supplied by a preproduction fixture is not real production authority. Live provider-backed, cross-client scope verification, owned promotion and controlled owner Teams arrival are still required before release. The existing V1 10-day fallback remains default.


## 2026-10-30 end-to-end preproduction evidence checkpoint

**Non-production source implemented:** The bounded `vulscan_microsoft_public_source.py` fetches only approved Microsoft Windows release-history pages and exact official KB articles with TLS, no credentials, redirected-host restrictions, size bounds and a separate read-authority check. It supports Windows 11, Windows 10 and Windows Server; a source discrepancy or missing exact KB fails closed. Known-issue claims remain absent until specifically verified; source article metadata is not itself proof that there are no known issues.

**Live nonmutating research evidence:** An authorized Jason read of one real Datto managed endpoint established that `endpoint.patch.search` returns an `evidence.items` array, rather than the obsolete `evidence.data.patches` test-fixture layout. An exact queried Windows KB showed `NOT_APPROVED` and a vendor release date of 2026-10-13; Microsoft Learn independently reported the same release date. No customer/device identifiers are persisted here. A bounded public Microsoft source run succeeded for one Windows 11 KB, one Windows Server KB, and one Windows 10 KB, retrieving their release dates and verified support-article summaries.

**Additional governed integration:** New read-only Datto capabilities `management.site.patch.search` and `endpoint.patch.policy.search` are declared in the existing Datto connector, manifest, resource capability catalog and invoker mappings. The policy and site patch readers require complete bounded pagination; missing or ambiguous policy/device/site identities must fail closed. `vulscan_v2_site_inventory.py` requires the full authorized client/site mapping, reads all scoped site patch records, verifies each device's exact Datto UID and site membership, and reads the device's assigned policies. `vulscan_v2_preproduction_factory.py` composes these source ports into dormant shadow mode. No new standalone Teams transport is permitted.

**Source checks:** Isolated source-level fixture acceptance includes Day 15/16/21, KB grouping, Windows known-issue omission, duplicate suppression, automatic recheck, injected Microsoft source rejection, canonical Teams audience checks, authoritative policy identity, cross-client isolation, complete site inventory, owner approval gate, failure/restart handling, and V1 10-day fallback behavior.

**Unresolved gates, DO NOT ACTIVATE:** The new Datto patch-policy/site-patch capabilities are not currently live in the user's production MCP catalog, so their real response payloads, completeness, and authorization cannot be accepted yet. A controlled preproduction provider-backed test is still required, including reconciliation against the documented deferral/decline record and complete customer/site binding. The V2 shadow helper is intentionally unregistered in active production composition. No direct Datto API or shell credential bypass is an acceptable substitute. The remaining production-manager evidence requires protected CI green, exact scope inventory, current last-known-good rollback SHA, health and rollout/rollback plan, and Owner exact-SHA deployment authorization.

**Aging policy remains:** V1 ten-day ticket aging is the default until V2 owner-supervision, canonical Teams authorization and real evidence pass exact promotion. Day 21 V2 follow-up does not implicitly move the ticket or approve a patch.



## 2026-10-30 safe-progress checkpoint — verified Owner exception source

**Section Goal:** Do not send a day-16/day-21 reminder while a technician or Owner has already deliberately deferred, declined, or superseded the exact KB, even if the Datto device currently reports `NOT_APPROVED`. Success requires an independently read, complete and fresh governance record before any notice is eligible.

**Provider-neutral decision contract:** `VerifiedPatchReviewDisposition` requires exact `kb`, `client_id`, `policy_id`, `device_uid`, explicit `review_pending | deferred | declined | superseded` disposition, authorized `source_reference`, `full_scope_verified=True`, and a timezone-aware read timestamp no older than 15 minutes. A `review_pending` result is an affirmative *complete-source attestation that there is no recorded exception for this exact scope*, not a default from an absent row. A missing record, stale timestamp, incomplete decision coverage, conflicting existing target flag, or cross-client mismatch blocks the entire notification batch. Verified `deferred/declined/superseded` suppresses the reminder. An already queued event must reread the same evidence before the shared Teams transport sends it.

**Implementation:** `vulscan_owner_disposition_evidence.py` now validates the decision record, and `vulscan_governed_patch_source.py`, `vulscan_v2_preproduction_workflow.py`, and `vulscan_v2_preproduction_factory.py` require an injected, separately governed owner-decision reader. **No new provider permission or live source was added.** If the trusted decision store is not accessible, shadow/queue evaluation returns a documented coverage error rather than treating unknown as allowed. An empty scoped patch inventory never creates a notification.

**Datto API contract to resolve in authorized staging:** Datto RMM's English API table documents `GET /v2/device/{deviceUid}/site/patch-management` for assigned policies and `GET /v2/site/{siteUid}/patches` for site patches, while its German API page documents `GET /v2/device/{deviceUid}/policies/patch-management` and the version 15.1 release notes describe site patches as `GET /v2/sites/{siteUid}/patches`. The branch currently uses `/device/{uid}/policies/patch-management` and `/site/{uid}/patches`. The public OpenAPI endpoint was inaccessible (HTTP 500); neither a web page nor a fixture proves live endpoint compatibility. **Require one authorized, governed, read-only provider-backed GET acceptance for each exact route and full pagination before activating the capability; never silently fall back to an alternate URL or use direct credential calls.** Any provider schema, missing exact device UID, incomplete site page, or absent signed owner-decision evidence fails closed.

**Acceptance:** Exact owner state and absence proof, verified fresh timestamps, cross-client isolation, deferral/decline/supersedence, queued-message reread, complete site/device policy inventory, Microsoft release date and KB article, Teams recipient authority, outbox no-replay and no direct patch/ticket mutation. Until those live sources and release authority pass, V2 remains *preproduction only* and V1 ten-day ticket handoff stays active.


## 2026-10-30 patch-policy attribution refinement (preproduction)

**Section Goal:** Attribute each unapproved Windows KB to the exact patch policy whose current evaluation actually disapproved it, without assuming that a device's effective `NOT_APPROVED` status applies to every assigned policy.

**Evidence gate:** Datto RMM can combine global/site patch policies and device-level overrides in a device's effective patch status. The assigned-policy list alone proves *assignment*, not why this KB was approved/disapproved. A new `VerifiedPolicyKBAttribution` read requires an exact KB + client + site + device UID, explicit current policy decision for **every assigned policy**, source reference, complete scope, and a timestamp within 15 minutes. Only explicit `NOT_APPROVED` policy decisions count toward an aging notice. `APPROVED_PENDING` and `NOT_APPLICABLE` assigned policies do not receive causal attribution. Contradictory states, missing records, stale evidence, incomplete policy coverage, and aggregate `NOT_APPROVED` with no attributable policy fail closed, including when the cause might be an unknown device-level override. No direct provider access or fallback is permitted.

**End-to-end contract:** The scoped site inventory must use a separate, authorized per-KB policy evidence reader before creating verified targets. Each target carries checked-at time and attribution provenance, and the downstream collector rejects unproven/stale targets even if bypassing the inventory adapter. The full shadow workflow's default factory has this reader unset; **activation is impossible without governed live source wiring and provider-backed acceptance**, in addition to the separate Owner defer/decline source.

**Current documented routes (Datto RMM API English v15.2, viewed 2026-10-30):** `GET /v2/device/{deviceUid}/policies/patch-management` and `GET /v2/site/{siteUid}/patches`. Current official English documentation supersedes an older search excerpt that temporarily showed `/device/{deviceUid}/site/patch-management`; 15.1 release notes separately contain a plural `/sites/{siteUid}/patches` spelling. The implementation uses the current English v15.2 paths in the read-only connector. Actual authorized API response shape and pagination **remain unverified** pending governed staging. Never attempt alternate paths behind the connector's permission checks.

**Acceptance still required:** Provider-backed assigned-policy and site-patch reads; complete page and client/device scope; causal per-KB policy rules or device override; signed current Owner deferral/decline/negative-exception source; stale queued-message recheck; Teams recipient and delivery; parallel V1 ten-day handoff reconciliation. No readiness claim from fixtures alone.
