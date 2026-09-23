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
2. Resolve the vendor.
3. Resolve any named customer/company.
4. Search for an existing PO, invoice, order confirmation, quote, or vendor order number.
5. Search likely open Autotask tickets for the customer/request context.
6. Read the likely ticket description and notes where authorized.
7. Present a likely ticket as: `TICKET-NUMBER — Ticket Title`.
8. Record why the candidate matched: customer, requester, vendor, product/SKU, device, title, notes, quote/order reference, or other grounded evidence.
9. Detect possible duplicate orders or existing inventory before proposing purchase.
10. If more than one material candidate remains, present the bounded candidate list instead of guessing.

If the procurement object, vendor, customer, or allocation cannot be identified confidently:

`state = identification_blocked`

---

## 5. Expected State

A healthy procurement case has:
- one resolved vendor;
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
- receiving quantities
- invoice/PO variance
- outstanding exceptions

Do not repeat already completed steps after a restart, recheck, or handoff.

---

## 7. Diagnostic Workflow

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
- vendor resolved;
- duplicate check complete;
- catalog match/create proposal resolved;
- customer context resolved when applicable;
- likely ticket presented with number + title when evidence supports one;
- allocation reconciles exactly;
- billable quantity explicitly determined or explicitly deferred;
- financial totals supported by evidence;
- required approval available.

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
- vendor;
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
