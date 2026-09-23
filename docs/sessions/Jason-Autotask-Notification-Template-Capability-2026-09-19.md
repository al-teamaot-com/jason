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

## 2026-09-20 continuation — ticket-note communication bridge

Autotask documents `TicketNotes` as a creatable/updatable REST entity. Its `publish` and `noteType` fields are picklists, and Autotask explicitly directs integrations to `/entityInformation/fields` to obtain tenant-specific picklist values. Numeric values must therefore not be assumed from another tenant or hard-coded from examples.

Implementation started on branch `feature/autotask-customer-communication-20260920`:
- add `TicketNotes` to the bounded approved schema-discovery entity set;
- add provider operation `autotask.entity.fields.describe` for `/V1.0/{entity}/entityInformation/fields`;
- add provider-neutral read capability `service.entity.fields.describe` and route it through the existing governed Autotask read path;
- add source tests for the TicketNotes field-schema route and canonical argument adapter;
- preserve all existing mutation/action surfaces unchanged until live picklist semantics are proven.

Next proof is intentionally read-only: deploy the schema read, retrieve `TicketNotes` field metadata, and identify the exact active `publish` values corresponding to internal-only and customer-visible behavior plus the intended `noteType`. Only after that proof should a distinct customer-visible note capability be implemented. The existing internal-note action must remain separate so an outward communication path cannot silently broaden an internal note.

## Section Goal closure
**PARTIAL / IMPLEMENTATION IN PROGRESS.** Template-use evidence is supported; direct named-template dispatch is not claimed because the vendor API does not document such an operation. A supported ticket-note communication bridge is now being developed without assuming tenant picklist IDs.

## Production permission diagnosis
Live provider preflight confirms `Resources` is queryable by the dedicated read identity (`userAccessForQuery=All`) while `NotificationHistory` is not (`userAccessForQuery=None`). The failure is therefore isolated to the read identity's Autotask security level. Jason has no governed Autotask security-level administration capability and will not use direct provider or private UI automation to broaden it. The required provider-side change is limited to enabling Notification History query access on the **Jason read-only API user's security level**. The separate `Jason API - Ticket Mutation` profile must remain unchanged.
