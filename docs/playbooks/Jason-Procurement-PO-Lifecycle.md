# Jason Playbook: Procurement Purchase Order Lifecycle

## 1. Section Goal

**Goal:**  
Allow Jason to manage an AOT purchase from request through verified Autotask PO creation, ticket/customer allocation, delivery monitoring, receiving, ticket billing, invoice reconciliation, and exception escalation without guessing financial or billing intent.

**Success means:**
- Jason resolves the vendor, customer context, requester, products/services, and any likely related Autotask ticket before proposing a PO.
- Any proposed ticket association always shows **ticket number + ticket title**.
- Every ordered unit has an explicit allocation such as customer/ticket, AOT inventory, or another approved destination; ordered quantity never implicitly equals billable quantity.
- Customer billing is a separate governed decision from PO association and is never inferred.
- Procurement changes requiring financial, master-data, billing, receiving, cancellation, quantity, vendor, or status mutation use the governed approval path.
- Delivery and vendor-email evidence can be correlated to the correct PO and proposed through Teams approval.
- Every approved mutation receives authoritative Autotask readback and quantity/cost reconciliation.
- Ambiguous, incomplete, duplicate, or contradictory evidence fails closed.

Do not consider the Section Goal complete until the controlled acceptance tests in Section 21 have been demonstrated and documented.

---

## 2. Trigger

This playbook applies when any of the following occurs:
- an authorized AOT technician asks Jason to create or update a purchase order;
- an approved vendor invoice/order confirmation is identified;
- an approved requester mailbox or central purchasing mailbox receives an order, backorder, shipment, ETA, cancellation, delivery, or invoice update correlated to an active PO;
- an Autotask ticket contains evidence that hardware/software/services must be ordered;
- an existing PO requires receiving, customer billing follow-up, or exception handling.

Jason must resolve the exact requester and procurement object before starting.

---

## 3. Scope and Boundaries

### In Scope
- Autotask Products, ProductVendors, Services, ServiceBundles, PurchaseOrders, PurchaseOrderItems, PurchaseOrderItemReceiving.
- Autotask company, contact, ticket, ticket-note, and configuration-item reads needed for correlation.
- Approved mailbox evidence.
- Teams approval/information-request workflow.
- Per-line allocation between customer/ticket and AOT inventory.
- Proposed ticket billing after explicit quantity and price/billing-policy confirmation.
- Delivery/ETA/tracking/backorder monitoring and exception handling.
- Invoice-to-PO reconciliation.

### Out of Scope
- assuming a PO quantity is fully customer billable;
- changing quantity, cost, vendor, cancellation, receiving, customer billing, or financial commitment without applicable authority/approval;
- treating an email alone as proof that inventory was physically received;
- creating duplicate catalog items, POs, ticket charges, or receiving transactions;
- bypassing Autotask's native PO lifecycle;
- direct provider access outside Jason governance.

Preserve:
- `direct_provider_access=false`
- Central Orchestrator authority
- exact requester grants
- provider/client isolation
- audit trail
- existing approval rules

---

## 4. Initial Identification

Before proposing or changing a PO:
1. Identify the requester.
2. Resolve the vendor to an exact Autotask vendor company ID.
3. Extract available vendor identity data from the quote, invoice, URL, or vendor website and reconcile it against Autotask before procurement continues. Compare, where present: legal/display name, website/domain, street/city/state/postal address, phone, vendor/account number, email, and other procurement-relevant identity fields.
4. Treat the incoming source as a freshness check on the Autotask vendor master record:
   - matching values become verification evidence;
   - source fields missing in Autotask become proposed vendor-master updates;
   - conflicting non-empty values require `state = vendor_review` and must not be silently overwritten;
   - absence of a field in the source is not evidence that the Autotask value is wrong.
5. Resolve any named customer/company.
6. Search for an existing PO, invoice, order confirmation, quote, or vendor order number.
7. Search likely open Autotask tickets for the customer/request context.
8. Read the likely ticket description and notes where authorized.
9. Present a likely ticket as: `TICKET-NUMBER — Ticket Title`.
10. Record why the candidate matched: customer, requester, vendor, product/SKU, device, title, notes, quote/order reference, or other grounded evidence.
11. Detect possible duplicate orders or existing inventory before proposing purchase.
12. If more than one material candidate remains, present the bounded candidate list instead of guessing.

If the procurement object, vendor, customer, or allocation cannot be identified confidently:

`state = identification_blocked`

---

## 5. Expected State

A healthy procurement case has:
- one resolved vendor with an exact Autotask vendor company ID;
- vendor master data compared against the current source evidence, with confirmed fields recorded and meaningful drift resolved or explicitly reviewed;
- one durable PO when a PO is required;
- normalized PO lines linked to approved catalog records;
- every ordered quantity explicitly allocated;
- customer allocations linked to a resolved customer and, when applicable, `ticket number + title`;
- AOT inventory allocations explicitly marked as non-customer-billable;
- no duplicate active order for the same approved requirement;
- costs/totals reconciled to approved evidence;
- delivery state supported by current evidence;
- receiving based on actual receiving evidence;
- customer billing quantity equal only to the explicitly approved customer allocation;
- receiving is recorded before release and never implies release;
- customer stock is not released until one exact ticket and one explicit billing disposition are persisted;
- client quote creation is an optional branch, independent of purchase-order creation, and is bound to one exact ticket;
- hardware billing is reconciled through TicketCharge -> BillingItem -> Invoice evidence with persisted exception states;
- complete audit linkage from request/invoice/email -> approval -> Autotask mutation -> readback.

---

## 6. State Model

Persist at least:

`identified -> correlating -> allocation_required -> approval_required -> approved -> ordered -> confirmed -> waiting_delivery -> partially_shipped -> shipped -> delivered_pending_receipt -> partially_received -> received -> billing_pending -> reconciled -> complete`

Alternative/exception states:

`identification_blocked`  
`duplicate_review`  
`backordered`  
`exception_review`  
`cancelled`  
`blocked`  
`escalated`

Persist:
- requester
- vendor
- customer
- PO ID/number
- vendor order/invoice references
- related ticket ID, number, title, and match evidence
- line items
- ordered quantity
- allocation quantities/destinations
- explicitly approved billable quantity
- expected delivery/ship dates
- tracking references
- email evidence identifiers/digests
- approval IDs and decisions
- create-PO selection and create-client-quote selection
- client quote ID and opportunity ID when created
- receiving quantities
- release state and release quantity
- billing disposition
- ticket charge ID
- billing item ID and invoice ID when posted/billed
- billing-audit evidence digest and last notification digest/state
- invoice/PO variance
- outstanding exceptions

Do not repeat already completed steps after a restart, recheck, or handoff.

---

## 7. Diagnostic Workflow

### Step 0: Resolve and verify vendor

**Purpose:** Confirm the supplier exists as the correct Autotask vendor entity and use the current source as a vendor-master freshness check.

**Evidence source:** Quote/invoice contents, pasted product URL, vendor website, and Autotask company/vendor reads.

**Expected result:** One exact Autotask vendor company ID with reconciled vendor identity evidence.

Compare available source fields to Autotask, including:
- legal/display name;
- website/domain;
- address;
- phone;
- email;
- vendor/account number;
- other stable procurement identifiers present in the source.

If no exact vendor exists -> retain the submission as a vendor-creation proposal. On explicit submission, use only the vendor-specific governed capability to create an Autotask company with `companyType = Vendor`; do not expose generic company creation. Persist the returned vendor ID before any product, quote, or PO mutation so retries cannot duplicate the vendor.
If Autotask is missing a value that is present in authoritative current source evidence -> propose a vendor-master update.
If both source and Autotask contain conflicting values -> `state = vendor_review`; do not silently update or continue financial commitment.
If the source does not expose a field -> retain the Autotask value and record that the source could not verify it.

### Step 1: Resolve catalog and existing procurement

**Purpose:** Determine whether the requested item already exists and whether it is already ordered or in stock.

**Evidence source:** Autotask catalog/inventory/PO reads.

**Expected result:** Exact approved catalog match and no unintended duplicate purchase.

### Decision
If an exact match exists -> reuse it.  
If multiple plausible matches exist -> `state = exception_review`.  
If no match exists -> propose catalog creation; approval required.

### Step 2: Resolve likely ticket

**Purpose:** Determine whether the purchase belongs to existing service work.

**Evidence source:** Autotask ticket search/read/notes.

**Expected result:** One strong candidate or an explicit no-ticket decision.

Jason must present candidates as:
`T20260920.0123 — Replace Accounting Workstation`

The candidate explanation should state the match evidence, not an unsupported confidence claim.

### Step 3: Reconcile line allocation

**Purpose:** Ensure every ordered unit has an intended destination.

For each line record:
- ordered quantity;
- customer/ticket quantity;
- AOT inventory quantity;
- other approved destination quantity, if applicable;
- bill-to-ticket flag and exact ticket;
- non-billable inventory flag.

**Invariant:**  
`sum(allocation quantities) == ordered quantity`

Example:
- Order: 2 x Dock
- Customer XYZ / `T20260920.0123 — Replace Accounting Workstation`: 1
- AOT Inventory: 1
- Billable ticket quantity: 1

If allocation does not reconcile exactly -> `state = allocation_required`.

### Step 4: Check duplicate and historical context

Search:
- open/recent POs;
- related ticket notes;
- recent invoices;
- existing inventory;
- same vendor SKU/customer/order reference.

A possible duplicate requires review before purchase.

### Step 5: Normalize vendor/email updates

Normalize supported events:
- order confirmed;
- ETA changed;
- backordered;
- partially shipped;
- shipped;
- tracking updated;
- delivered;
- cancellation requested/confirmed;
- invoice received;
- price/quantity changed.

Correlate using multiple grounded identifiers where available: PO number, vendor order number, invoice number, vendor, requester, SKU/product, customer, dates, and ticket context.

Email evidence must not by itself mark physical inventory received.

---

## 8. Decision Gates

Before PO creation:
- requester identity resolved;
- requester delegated spending authority resolved from the AOT internal Autotask contact (`companyID = 0`) and its `Spending limit` UDF;
- vendor resolved to an exact Autotask vendor company ID;
- vendor source-vs-Autotask reconciliation completed with no unresolved conflicting identity data;
- duplicate check complete;
- catalog match/create proposal resolved;
- customer context resolved when applicable;
- likely ticket presented with number + title when evidence supports one;
- allocation reconciles exactly;
- billable quantity explicitly determined or explicitly deferred;
- financial totals supported by evidence;
- total AOT cost commitment includes product cost, freight, tax, and fees;
- required approval available only when the total commitment exceeds the requester's delegated `Spending limit`; at or below the limit, do not generate approval noise merely to state that approval was unnecessary.

Before ticket billing:
- exact ticket resolved;
- ticket number + title shown to approver;
- customer allocation quantity known;
- billable quantity explicitly approved;
- approved selling price/billing policy available;
- duplicate ticket charge check completed.

Before receiving:
- exact PO item resolved;
- quantity being received does not exceed authorized outstanding quantity;
- actual receipt evidence exists;
- serial numbers captured when required.

---

## 9. Remediation / Authorized Actions

### Create/update catalog record
**Approval classification:** modifying/high-risk master data.  
**Verification:** Autotask readback of durable record.

### Create/update PO or PO item
**Approval classification:** financial/modifying.  
**Verification:** PO/item readback and total/quantity reconciliation.

### Add informational PO/ticket note
**Approval classification:** may become standing low-risk policy after separate approval. Until then, follow normal write governance.

### Customer ticket billing
**Approval classification:** financial/customer-impacting.  
**Rule:** PO association never grants billing authority. The approved ticket-billing quantity may be less than ordered quantity.

### Receive item
**Approval classification:** inventory/financial state mutation.  
Use `PurchaseOrderItemReceiving`; do not directly patch a PO to Received Full.

### Teams approval
Approval evidence must include:
- submitted by / requester;
- requester Autotask contact ID and spending limit used for the decision;
- vendor and exact Autotask vendor company ID;
- vendor verification/drift summary;
- PO/order reference;
- customer;
- ticket number + title;
- exact line/SKU/product;
- ordered quantity;
- customer/ticket allocation;
- AOT inventory allocation;
- billable quantity;
- cost and relevant variance;
- proposed exact Autotask changes;
- source evidence summary.

Typed overrides are modified instructions, not implicit approval.

---

## 10. Retry Policy

- Maximum provider mutation attempt per approved action: `1`.
- Never retry a financial/create/receive mutation without first determining whether the provider accepted the first request.
- Duplicate-safe readback is mandatory before any retry proposal.
- Email correlation may be re-evaluated when new evidence arrives; do not generate duplicate approval requests for materially identical evidence.

---

## 11. Periodic Rechecks

For active unreceived POs:
- recheck on new correlated vendor email immediately;
- otherwise perform scheduled aging review at an approved cadence;
- suppress duplicate checks/notifications for unchanged evidence.

Recheck:
- current PO state;
- ETA;
- backorder status;
- tracking;
- received/outstanding quantity;
- invoice status;
- related ticket state;
- billing status.

Stop when complete, cancelled, escalated, or otherwise terminal.

---

## 12. Aging / Stale Condition

Escalate when:
- ETA passes without delivery evidence;
- shipment remains partial beyond expected completion;
- PO is received but ticket billing remains pending;
- invoice exists but receipt/PO reconciliation remains unresolved;
- delivered equipment has no receiving confirmation after the approved threshold;
- vendor correspondence conflicts with Autotask quantities/costs;
- related ticket is completed while procurement remains outstanding.

---

## 13. Dependency Handling

Explicit dependencies:
- governed mailbox/message search and read for approved requester/central purchasing mailboxes;
- attachment extraction where required;
- Teams approval/information-request completion;
- Autotask ticket billing/product-charge capability if not already exposed;
- inventory availability/read capability sufficient for duplicate/stock checks;
- persisted procurement state and scheduled recheck support.

If a dependency is unavailable:
1. record the missing capability;
2. do not simulate it;
3. use available evidence only;
4. set `state = blocked` where the missing dependency prevents safe continuation;
5. create/update the appropriate Project Jason TODO/support item rather than bypassing governance.

---

## 14. Documentation Requirements

Document meaningful steps in the related ticket and/or procurement case:
- vendor/request evidence;
- catalog match;
- ticket candidates and selected ticket number + title;
- allocation;
- billing decision;
- approval ID/decision;
- PO mutation/readback;
- delivery update;
- receiving;
- invoice reconciliation;
- exceptions.

Never record mailbox secrets, authentication tokens, API keys, or unnecessary message content.

Suggested note titles:
- `Jason - Procurement - Ticket Association`
- `Jason - Procurement - Allocation`
- `Jason - Procurement - PO Approval`
- `Jason - Procurement - Delivery Update`
- `Jason - Procurement - Receiving`
- `Jason - Procurement - Ticket Billing`
- `Jason - Procurement - Reconciliation`
- `Jason - Procurement - Exception`

---

## 15. Failure Handling

Treat as first-class failures:
- pasted URL cannot be safely retrieved or resolved;
- vendor cannot be matched to an exact Autotask vendor company;
- vendor source data conflicts with the Autotask master record;
- mailbox read unavailable;
- email cannot be correlated safely;
- ticket match ambiguous;
- allocation does not reconcile;
- missing catalog data;
- duplicate order suspected;
- cost/quantity mismatch;
- approval response cannot be authenticated/correlated;
- mutation succeeds but readback fails;
- receipt quantity exceeds outstanding amount;
- billable quantity/price is unknown;
- provider returns an unexpected PO status.

Never silently substitute an assumption.

---

## 16. Escalation Criteria

Escalate for:
- unresolved duplicate;
- ambiguous customer/ticket;
- financial variance requiring management judgment;
- cancellation/return/RMA not covered by approved policy;
- unmatched delivered item;
- repeated vendor delay;
- conflicting email/provider evidence;
- unsupported billing rule;
- provider/authority failure;
- unresolved allocation.

Escalation must summarize evidence, current allocation, proposed next action, and the relevant ticket number + title.

---

## 17. Verification

A procurement action is verified only when:
- the exact approved Autotask mutation reads back successfully;
- line quantities and allocations still reconcile;
- PO totals/costs match approved evidence within policy;
- receiving totals equal actual authorized receipts;
- ticket billable quantity equals the approved customer allocation, not the order quantity;
- no duplicate ticket charge was created;
- final PO state is consistent with native Autotask lifecycle.

---

## 18. Completion Criteria

Complete only when:
1. PO and lines are reconciled;
2. every unit has a final allocation;
3. all required receiving is complete or an approved exception disposition exists;
4. customer-billable quantities were added to the correct ticket when required;
5. AOT inventory quantities were not billed to the customer;
6. invoice/PO/receipt variances are resolved;
7. related ticket/procurement documentation is complete;
8. outstanding approval/recheck jobs are cleared.

---

## 19. Final Resolution Note

Include:
- requester
- vendor
- PO
- customer
- related `ticket number — title`
- ordered quantities
- final customer allocation
- final AOT inventory allocation
- billable quantities
- delivery/receiving result
- invoice reconciliation
- approval references
- final disposition

---

## 20. Required Capabilities

Currently available/partially available:
- Autotask product/service/catalog reads and governed writes;
- Autotask PO/PO-item reads and governed writes;
- Autotask PO receiving;
- Autotask ticket search/read/notes;
- Autotask ticket create/update/internal note;
- Teams proactive message/card transport foundation.

Required implementation dependencies to verify/complete:
- approved mailbox/message content search/read;
- message attachment read/extraction;
- deterministic Teams approval + typed override terminal processing;
- exact Autotask ticket billing/charge capability and duplicate-charge readback;
- inventory availability/allocation read sufficient to distinguish AOT stock from customer allocation;
- persisted procurement case state;
- scheduled procurement aging/recheck.

Do not broaden capabilities solely for convenience.

---

## 20A. Unified Procurement / Inventory / Billing Controls (2026-10-02)

This section reconciles GitHub issues `#727`, `#728`, and `#731` into this single lifecycle. No separate procurement, quote, inventory-release, or billing-audit workflow may bypass this state model.

### Vendor quote / invoice / URL branch

The normalized source record may originate from a vendor quote, vendor invoice, or pasted product URL. All sources converge on the same product/vendor normalization, duplicate prevention, ticket resolution, allocation, approval, and audit path.

The Teams card exposes independent controls:

- **Create purchase order** — financial commitment branch.
- **Create client quote** — customer-facing Autotask quote branch.
- neither selected — catalog/part normalization only.

The controls are independent. Creating a client quote does not create a PO. Creating a PO does not create a client quote unless explicitly selected.

### Explicit ticket rule for client quotes

A client quote may be created only when one exact Autotask ticket has been resolved and persisted. The quote audit record must retain ticket ID/number/title/company, created Opportunity ID, created Quote ID, created QuoteItem IDs, and source/procurement submission ID.

API-created Autotask Quotes must be associated with an active Opportunity. Jason therefore creates the governed Opportunity first, then the Quote, then its QuoteItems, with post-write readback at every step.

### Mixed allocation rule

Each line persists ordered quantity, customer quantity, AOT stock quantity, and the exact customer ticket where customer quantity > 0.

Hard invariant:

`ordered_quantity = customer_quantity + aot_stock_quantity`

Negative quantities, over-allocation, under-allocation, or customer allocation without an exact ticket fail closed.

### Receiving is not release

Receiving and stock release are different lifecycle transitions:

`ordered -> received_pending_disposition -> ready_for_release -> released`

Receiving proves physical receipt only. It does not authorize handing customer-designated stock to a technician/client.

Customer stock may transition to `ready_for_release` only when all are true:
1. required units are physically received;
2. one exact ticket is persisted;
3. billing disposition is `charge_created`, `existing_unbilled_charge`, `no_charge_contract`, `no_charge_warranty`, or `no_charge_internal`;
4. allocation math still reconciles;
5. no unresolved billing exception exists.

AOT-stock-only quantity may be received into inventory without a customer ticket or customer billing disposition.

### Hardware billing leakage audit

For customer-designated hardware, persist one case key per expected ticket/product allocation with state, exact ticket, product, expected quantity/price, ticket charge ID, BillingItem ID, Invoice ID, evidence digest, first-detected time, technician disposition, due date, last-notified state/digest/time, and escalation time.

State transitions:
1. no matching ticket charge -> `technician_disposition_pending`;
2. matching charge exists with `isBilled = false` -> `existing_unbilled_charge`;
3. charge exists but quantity/price is wrong or ambiguous -> `billing_exception`;
4. `isBilled = true` but no exact BillingItem references the ticket charge -> `invoice_reconciliation_exception`;
5. BillingItem exists but invoice/quantity/rate does not match -> `invoice_reconciliation_exception`;
6. exact TicketCharge -> BillingItem -> Invoice evidence matches -> `reconciled`.

`existing_unbilled_charge` is not treated as a missing-charge case and must not create a duplicate charge.

### Technician Teams disposition

Only missing-charge cases require the concise technician card. Permitted dispositions are **Charge needed**, **Not billable**, and **Already handled**. The card must not repeat when the persisted state and evidence digest are unchanged.

### Two-business-day Lori escalation

When a missing-charge / technician-disposition case remains unanswered for two business days, escalate once to Lori. Persist the escalation timestamp so unchanged evidence does not generate duplicate escalation noise. The counter excludes Saturday and Sunday; holiday-calendar integration can be added without changing the persisted due-date contract.

### Invoice line verification

Customer invoice reconciliation uses Autotask `BillingItems`. The exact relationship is `BillingItem.ticketChargeID -> TicketCharge.id`, with `BillingItem.invoiceID` identifying the customer invoice.

Verification requires the exact ticket charge, exact BillingItem, expected quantity, expected sell price/rate, non-null invoice ID, and customer invoice readback/status/date when available. A TicketCharge reporting billed status without the exact posted BillingItem is an exception, not successful reconciliation.

### Retry / duplicate rules

- Persist state before notifying.
- Suppress Teams notification when both state and evidence digest are unchanged.
- Never create a second ticket charge merely because the existing charge is unbilled.
- Never create a second client quote on retry after successful quote readback.
- Never repeat a write without first proving whether the first provider call was accepted.
- Changed quantity, price, ticket, invoice linkage, or provider state produces a new evidence digest and may generate a new notification.

---

## 21. Acceptance Test

Use a controlled AOT test purchase with two identical items:
- quantity ordered: `2`;
- quantity allocated to a test customer/ticket: `1`;
- quantity allocated to AOT inventory: `1`.

Prove:
1. Jason finds a likely ticket and presents **ticket number + title**.
2. Jason explains the ticket-match evidence.
3. Jason requires allocation because ordered quantity alone is insufficient.
4. The allocation reconciles `2 = 1 customer + 1 inventory`.
5. Teams approval shows the exact customer/ticket and inventory split.
6. PO creation/addition uses quantity 2.
7. Ticket billing proposal uses quantity 1 only.
8. A vendor ETA/shipping email correlates to the PO and produces an approval/information update without receiving the item.
9. Actual receipt can receive the appropriate item quantity through Autotask.
10. All writes receive readback verification.
11. A deliberate allocation mismatch fails closed.
12. A deliberate ambiguous-ticket case presents candidates rather than guessing.
13. State survives a new conversation/recheck.
14. Final notes reconcile PO, inventory, ticket billing, and receiving.
15. With Create PO unchecked, Jason normalizes the part and does not create a PO.
16. With Create Client Quote checked, Jason requires one exact ticket and creates Opportunity -> Quote -> QuoteItem without creating a PO unless Create PO is also checked.
17. A mixed allocation `2 = 1 customer + 1 AOT stock` remains persisted through PO creation.
18. Physical receiving alone leaves customer stock in `received_pending_disposition`; release is denied until the ticket and billing disposition are present.
19. An existing matching `isBilled=false` ticket charge becomes `existing_unbilled_charge` and no duplicate charge is created.
20. A billed charge without a matching BillingItem becomes `invoice_reconciliation_exception`.
21. Exact TicketCharge -> BillingItem -> Invoice quantity/rate verification becomes `reconciled`.
22. An unchanged technician billing exception does not generate a duplicate Teams card.
23. An unanswered missing-charge case becomes eligible for one Lori escalation exactly two business days after first detection.

Do not use a real client charge for the first acceptance test unless specifically approved.

---

## 22. Section Goal Closure

When acceptance succeeds:
- document implementation and capability additions;
- preserve test correlations and readback evidence;
- record known limitations;
- update Grafana / Project Jason Section Goal;
- update `TODO-OPS-007`;
- create explicit follow-up TODO/support items for any blocked mailbox, Teams approval, billing, inventory, or scheduling capability;
- mark the Section Goal complete only after end-to-end evidence proves the workflow.
