# Jason Autotask Notification Template Capability — 2026-09-19

## Section Goal
Give Jason governed access to Autotask notification-template evidence and a safe path toward template-based end-user communication without bypassing ticket/company isolation, audience controls, or write approval.

## Provider finding
Autotask's documented REST API does not expose Notification Templates as a queryable or executable template resource. The documented `NotificationHistory` entity is query-only and exposes recent notification evidence including `templateName`, recipient, sent time, company, and ticket. `TicketNotes` supports create/update but does not provide a template-selection or recipient-send operation. Therefore Jason must not invent an undocumented template-send endpoint or use private Autotask UI calls.

## Implemented foundation
- Added provider-neutral read capability `service.notification.history.search`.
- Added documented Autotask `NotificationHistory/query` provider operation.
- Search is fail-closed unless an explicit `company_id` is supplied; optional `ticket_id` and exact `template_name` further narrow the evidence.
- Added Notification History as an Autotask Integration Broker resource and registered the runtime route.
- Existing Autotask provider authorization and Central Orchestrator boundaries remain authoritative.
- Focused connector/activation/argument-adapter tests pass, including a regression proving unbounded notification-history access is rejected.

## Next acceptance
Deploy the read capability and prove a same-company notification-history query in production. Then use the observed template names to build an AOT-approved communication-template catalog. Actual dispatch must use a supported provider surface. If Autotask cannot invoke a named template through a supported API, dispatch should be implemented through a governed AOT communication capability while preserving the approved template's audience/purpose rather than scraping/private-calling the Autotask UI.

## Section Goal closure
**PARTIAL / READ FOUNDATION READY FOR PRODUCTION PROOF.** Template-use evidence is supported; direct named-template dispatch is not claimed because the vendor API does not document such an operation.

## Production permission diagnosis
Live provider preflight confirms `Resources` is queryable by the dedicated read identity (`userAccessForQuery=All`) while `NotificationHistory` is not (`userAccessForQuery=None`). The failure is therefore isolated to the read identity's Autotask security level. Jason has no governed Autotask security-level administration capability and will not use direct provider or private UI automation to broaden it. The required provider-side change is limited to enabling Notification History query access on the **Jason read-only API user's security level**. The separate `Jason API - Ticket Mutation` profile must remain unchanged.

## Approved-response and template-request extension

Jason now has a provider-neutral approved communication-template catalog plus a durable template-gap request workflow. This addresses the operational need for approved client responses without pretending that Autotask exposes Notification Template bodies through its documented REST API.

When no approved catalog entry matches the required purpose/audience, Jason may autonomously create or strengthen a Communication Template Request. `PROMPT-COMM-001` drafts structured reusable content only; deterministic `render_aot_html()` applies the established AOT HTML shell. The proposed subject/body and required variables are stored for AOT review. Proposed templates are not approved and cannot be used as send authority until explicitly reviewed/published.

The initial approved catalog is intentionally empty pending import/review of AOT's existing approved templates. This avoids fabricating approved wording from observed Notification History names alone.
