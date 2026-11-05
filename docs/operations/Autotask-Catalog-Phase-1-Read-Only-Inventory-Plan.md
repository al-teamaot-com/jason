# Autotask Inventory Cleanup — Phase 1 read-only inventory and audit preparation

**State:** Prepared for review; **not executed**. No inventory extraction or catalog mutation is asserted.
**Agreement:** [Approved Version 1.4 — Goal, Scope, and Definition of Success](Autotask-Inventory-Cleanup-Agreement.md), Owner approval 2026-11-05.
**Workstream priority:** Independent; does not supersede production reliability, tickets, or existing approved engineering.
**Authority:** Preparation and authorized governed read-only discovery. **No** catalog modification, financial changes, provider permission changes, new API identity, contract mutation, production release or service restart.

## 1. Objective and bounded deliverables

Phase 1 establishes a **complete, evidence-backed accounting of all accessible active and inactive** Autotask Products, Services, Service Bundles, and relevant Contract relationships. Classification and audit findings are the deliverable, **not correction**.

Produce these versioned or appropriately secured artifacts:

1. **Inventory manifest:** source entity, source record ID, state (active/inactive/unknown), available classification, observed source timestamp, evidence reference, relevant dependency presence, and any source-access limitation. Avoid unnecessarily exporting client-sensitive pricing or contractual details to broadly visible locations.
2. **Coverage ledger:** for each entity, source population/count evidence (when supported), requests/page cursors, unique retrieved IDs, duplicate or skipped pages, reconciliation result, inaccessible/unknown records, and stated denominator.
3. **Dependency map:** current references from Contracts and bundles to catalog records, scoped to verified company/contract authorization. Distinguish confirmed links from inferred associations or inaccessible relationships.
4. **Data-quality findings:** missing/ambiguous applicable fields; potential duplicate groups based on identifiers, unit, vendor, description and functional equivalence; retired/inactive with present-day dependencies; unverified vendor cost; inconsistencies between catalog price and approved AOT policy if an authoritative policy is actually available.
5. **Exception register:** identifier, affected records, evidence, impact/severity, owner, disposition, next step, review date, and effect on dependent phases.
6. **Candidate treatment plan:** propose preferred records and the Phase 2 Product / Phase 3 Service standardization populations without making changes. Names in the historical catalog do not automatically require correction.
7. **Phase 1 acceptance evidence:** reproducible extraction configuration, query boundaries, counts, actual pagination/readback evidence, and acceptance disposition.

## 2. Live governed read capability discovery — 2026-11-05

Jason MCP reports status=ok, governed_execution=central-orchestrator, direct_provider_access=false. These read capabilities are **registered active and report authority_outcome=allowed** for the connected requester:

| Inventory object | Active governed reads | Observed search selectors |
| --- | --- | --- |
| Products | service.product.search, service.product.read | name, sku, resource_id, filters, page_size, after_resource_id |
| Services | service.service.search, service.service.read | name, resource_id, filters, page_size, after_resource_id |
| Service Bundles | service.service.bundle.search, service.service.bundle.read | name, resource_id, filters, page_size, after_resource_id |
| Contracts | service.contract.search, service.contract.read | company_id, contract_name, contract_number, status, contract_type, contract_category, resource_id, filters, page_size, after_resource_id |

**Important:** The registry confirms tool exposure and reported caller authority, **not** successful full enumeration, actual record pagination, financial-field release, or cross-company disclosure authorization. Contract reads are client-isolation-required. service.entity.describe and service.entity.fields.describe are also active for schema inspection, subject to their own authorization rules.

Separate preproduction evidence from 2026-11-04 (draft PR #2308) documents bounded, GET-only provider reads on the **existing** RW credential for Products, Services, ProductVendors, ServiceBundles, Contracts, BillingItems and Invoices. It does not establish that this caller's generic governed read path can access every commercially sensitive field, and does not authorize new extraction paths.

ContractServices is the **known relationship-coverage gap**: readonly credential metadata reports no query access; the existing RW identity reports Restricted. Draft PR #2312 contains dormant, non-registered scoped-read code and tests. **Do not** use its dormant source for provider reads, widen generic permissions, substitute raw API access, or claim full contract-service completeness until a separate approved, client-bound, governed read integration and provider-backed acceptance exist. Initial Phase 1 may proceed on independent catalog objects while this dependency remains explicitly open.

## 3. Read-only extraction procedure (planned, not run)

1. **Preflight:** verify current authorized requester identity and organization, active read capabilities, provider health, pagination contract, stable record selectors, query permissions, and data-handling classification.
2. **Capture baseline:** note extraction time window, source identity/permission mode, entity schema and usable fields. Record all active and inactive status values exactly as returned; do not infer missing statuses.
3. **Enumerate:** use governed search calls in bounded pages. Advance only with supported after_resource_id/continuation semantics; assert progress and stable unique record IDs. Retry transient failures with bounded backoff and deduplication; record every retrieval gap. If reliable pagination is unsupported, mark enumeration incomplete.
4. **Verify coverage:** use native provider count or independent count evidence where supported. Cross-check recorded page totals against unique IDs, query predicates, status partitions and any source-side limits. Never extrapolate sampled pages to a full inventory.
5. **Inspect applicable fields:** classify required, conditionally required, optional, unknown, and not applicable based on source schema and AOT standards still to be formally adopted. An unknown field value is not complete.
6. **Map dependencies safely:** use supported governed reads and permitted company/contract scope. Do not disclose contract or customer information across requester boundaries. If the relevant association is unavailable, record a coverage exception.
7. **Identify duplicate candidates:** deterministic evidence from IDs, SKU/manufacturer part numbers, vendor, unit, technical features and service semantics; never merge solely on name similarity. Record candidate clusters, not final duplicate findings without corroboration.
8. **Classify corrections:** active and inactive/currently referenced first; inactive/no-current-dependency remains inventoried but not automatically standardized. Preserve legacy names and prices.
9. **Publish findings:** create a concise summary, completeness ledger, and proposed correction-plan scope. Keep sensitive record-level exports in appropriately restricted storage and use sanitized engineering evidence.
10. **Gate Phase 2:** seek Owner/authorized approval only after presenting the exact Phase 2 correction population, field changes and validation/rollback criteria. Phase 1 discovery does not confer any write authority.

## 4. Measurable Phase 1 acceptance criteria

- **Population accounting:** 100% of **accessible** records in the agreed entity and status scope appear exactly once in the manifest, evidenced by complete pagination, unique ID reconciliation and source counts or alternative verified coverage evidence. Provider-inaccessible or unenumerable populations are **excluded from the accessible denominator only when separately counted and explicitly disclosed**; they are not silently counted as retrieved.
- **Classification:** every accessible record receives an active/inactive/unknown disposition and a priority treatment group. Unknown statuses remain open exceptions.
- **Dependency coverage:** each examined current Contract/bundle relationship receives verified mapping or a scoped, tracked exception. No claim of complete ContractServices coverage while the governed read path is unavailable.
- **Audit findings:** duplicate candidates, missing critical fields and questionable financial data are classified with evidence, not silently amended.
- **Exception handling:** each open noncritical issue has a disposition, owner, next action and review date; critical issues affecting safe acceptance block affected scope.
- **Read-only proof:** all access is through existing authorized governed read capabilities. Provider mutations, financial changes, secret extraction, unauthorized client disclosures, deployments and permission changes are zero.
- **Reporting:** execution completion, inventory coverage, data-quality coverage, financial verification, and exceptions are reported separately; a partially covered population is not "fully audited."

**Phase 1 cannot be declared accepted simply because a few searches succeed.** The approved agreement permits *Accepted with Exceptions* only when required work and applicable acceptance checks have been verified; a critical gap in the ability to account for the required population remains a blocker.

## 5. Dependencies, risks and continuation

| Condition | Treatment |
| --- | --- |
| Full enumeration not established by read search/page contract | Engineering or adapter preproduction work; no bypass; continue other entities |
| Client-restricted Contract/ContractServices data | Fail closed unless trusted requester/company binding and release gate pass |
| Existing autotask.readonly cannot read ContractServices | Record relationship gap; use only reviewed future governed RW-scoped read path |
| Unverified vendor cost | Preserve existing value, record exception, do not claim financial accuracy |
| Duplicate or obsolete record | Recommend preferred record; do not rename, inactivate or merge without approved correction plan |
| Catalog-write tools appear in registry | Registry exposure is not approval; **do not execute** under Phase 1 |
| Unrelated ongoing Project Jason engineering | Keep branch/PR isolated and avoid interfering with work or changing priorities |
| Future production activation of maintenance/validation | Separate code review, provider-backed verification, rollback and exact-SHA Owner approval |

## 6. Cross-system field portability requirement (2026-11-05)

**Owner direction:** When standardizing IT Products and Services, the resulting identifiers, names, descriptions and part numbers must remain usable in downstream systems such as QuickBooks. This is a **design and acceptance constraint**, not authorization to rename or modify records. The governing Version 1.4 agreement remains unchanged.

**Verified published QuickBooks field limits (Intuit):**

- QuickBooks Desktop Item Name/Number: **31 characters**. Desktop Item Part Number: **31 characters**; invoice item description: **3,975 characters**. Source: https://quickbooks.intuit.com/learn-support/en-us/help-article/printing-preferences/character-limitations-fields-quickbooks/L7eIy5gE3_US_en_US
- QuickBooks Online Item Name: **100 characters**, SKU: **100 characters**, and Item Description: **4,000 characters** according to Intuit's Item property reference. Source: https://static.developer.intuit.com/sdkdocs/qbv3doc/ippdotnetdevkitv3/html/850f7b3b-9e8b-679d-9389-6a487f859b39.htm

**Controls before any approved IT Product or Service correction plan:**

1. AOT uses **QuickBooks Online**, with previous governed proof identifying **QuickBooks Online Plus**. A fresh governed company read succeeded for the live AOT company on 2026-11-05, although the current response did not expose the subscription-plan field. Confirm AOT's configured Autotask-to-QBO integration and mappings before concluding which connector/import limits apply. Published field maximums are references, not proof of the effective connector limit; apply the shortest **verified** limit to each mapped export value.
2. Define separately: a stable short name / accounting item key, the complete human-readable description, manufacturer part number, preferred vendor part number or SKU, product category, billing unit, and source/target durable IDs. Do not concatenate every specification into the short name.
3. Prefer concise, client-readable Product and Service names while preserving full descriptions and identifiers in their authoritative fields. **Do not impose QuickBooks Desktop's 31-character item-name limit on AOT's QuickBooks Online integration as a verified requirement.** QBO's published 100-character Item Name limit is the relevant starting reference, subject to the actual Smart Accounting Hub mapping and any narrower downstream constraint. A shorter human-readability style guideline may be proposed without mandatory mass renaming.
4. Before importing or syncing, check field lengths, required values, character-encoding or unsupported character restrictions, uniqueness/case rules, mappings, effective accounting line description and any third-party integration constraints.
5. **No silent truncation**, invented part numbers, loss of leading zeroes, conversion of long identifiers to scientific notation, or collisions between different Products/Services. Any necessary alias/crosswalk must be deterministic, reversible, uniquely mapped and explicitly approved as part of the applicable correction plan.
6. Test a representative pilot through the actual authorized target-system integration with readback or safe import-preview evidence and no unintended accounting modifications. Where target write/import testing itself can affect accounting records, require a separate exact authorization before doing it.
7. Flag nonportable existing records as standards findings, **not** justification for mass renaming or cross-system mutation.

**Acceptance gate:** No proposed Product/Service naming standard is considered production-ready until the relevant mapped fields have verified target-system limits and a passing functional mapping test, or the unverified integration is disclosed as a blocking exception for the affected sync.

## 7. Future-system compatibility — design constraint only (Owner clarification, 2026-11-05)

**Scope boundary:** The Owner raised client-readable downstream documents solely to ensure that **IT Product and Service standardization is compatible with the fields and capacities of existing platforms**, particularly Autotask and QuickBooks Online. **AOT is not starting any invoice, billing reconciliation, monthly device/license collection, invoice template, or integration-configuration work under this step.** These remain later-phase subjects requiring their own agreed scope and applicable approvals.

Before proposing any naming, description, SKU or part-number convention:

- Determine each relevant *source and destination field*, its supported length, accepted characters, uniqueness rules, required values, and the actual native integration/export mapping. Do not assume an Autotask field and a QuickBooks field have the same capacity or function.
- **Never put a 20-character part number into a 10-character destination field.** Retain the complete manufacturer/vendor identifier in a suitable authoritative field, and propose a separate, validated short display name or deterministic crosswalk only when needed and approved. No arbitrary truncation, loss of leading zeros, scientific-notation conversion, or identifier collisions.
- Keep short human-readable names distinct from complete product descriptions, manufacturer part numbers and vendor SKUs. Preserve the details in their appropriate fields rather than making any one field do all jobs.
- Prefer existing native fields and platform capabilities. Propose only field-safe, understandable catalog conventions now; evaluate actual invoice presentation or automated monthly quantity reconciliation **later**, when the Owner explicitly opens that stage.
- Findings from static provider schema and mapping inspection are advisory. No catalog, invoice, contract, pricing or integration change is authorized by this note.

## 8. IT Product field constraints and proposed naming rule — Step 5 (2026-11-05)

**Status:** Verified field-metadata reconnaissance + **draft convention for Owner review** only. No policy, standardization correction plan or bulk operation has been approved; no Product record was modified.

### Verified Autotask Products REST field definitions

A bounded, authorized Jason `service.entity.fields.describe` read for `Products` returned 29 fields and these declared native field limits and validation attributes:

| Native Autotask Products field | Declared characters | Native requirement / intended interpretation |
| --- | ---: | --- |
| `name` | 1,000 | Required; catalog display name |
| `description` | 2,000 | Optional; descriptive specification / narrative |
| `sku` | 50 | Optional; SKU, **not automatically manufacturer part number** |
| `vendorProductNumber` | 50 | Optional; vendor-associated product number, **not automatically manufacturer part number** |
| `manufacturerName` | 100 | Optional; verified manufacturer / brand |
| `manufacturerProductName` | 50 | Optional; verified manufacturer product/model name |
| `internalProductID` | 50 | Optional; native identifier field (do not repurpose without schema confirmation) |
| `externalProductID` | 50 | Optional; native identifier field (do not repurpose without schema confirmation) |

The native field metadata does **not** expose a field explicitly called `manufacturerPartNumber`. Do not silently substitute `vendorProductNumber` or invent a manufacturer part number. Determine AOT's actual part-number source, meaning and appropriate native destination before requiring a field. Other relevant native fields include `productCategory`, `defaultVendorID`, `unitCost`, `unitPrice`, `productBillingCodeID`, and `isActive`; their detailed policy is outside this single naming step.

### QuickBooks Online reference limits — mapping not yet verified

- Intuit QBO Item API: `Name` **100 characters**, unique; `Sku` **100**; `Description` **4,000**. Source: https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/Item
- A newer QBO batch-import help article separately lists **512 characters** for Product/category name, **100** for SKU and **4,000** for descriptions. **Bulk-import UI rules are not proof of the API/Autotask sync rules.** Source: https://quickbooks.intuit.com/learn-support/en-us/help-article/list-management/import-products-services-quickbooks-online/L4o3mXx2u_US_en_US
- Kaseya's October 26, 2026 Smart Accounting Hub enhancement describes **Autotask billing-code to QBO Item** mapping, not a universal one-to-one Product `name` to QBO Item `Name` link. Verify the specific AOT workflow before enforcing a shared length restriction. Source: https://www.kaseya.com/platform/innovations/smart-accounting-hub-quickbooks-online-enhancements/

### One proposed naming decision (not yet approved)

**For genuine IT Products, prefer a concise, recognizable `Manufacturer Model Product-Type` display name**, for example `Dell OptiPlex 7020 Desktop` *if all components are verified*. Do not include a full specification list or arbitrary part number in the short display name. Place specifications in `description` and confirmed manufacturer/vendor identifiers in verified appropriate fields. Where manufacturer/model is not known, **leave the existing value unchanged and record a verification exception**, rather than fabricate values. No universal shorter numeric target is finalized until AOT's real downstream mapping is known; target human readability and fit within the tightest **verified mapped** field.

Pending Owner decision: whether to accept `Manufacturer Model Product-Type` as the **starting display-name convention** for the IT Product pilot. Approval of the convention would **not** authorize any record updates, invoice activities, billing edits or bulk processing.

## 9. IT Service naming convention — category-specific draft for Owner review (2026-11-05)

**Scope:** Read-only schema analysis and proposal, not final naming policy, an authorized correction plan, billing configuration or a Service record write. The earlier `Manufacturer Model Product-Type` proposal applies only to physical Products when relevant and verified; **it does not apply to Services by default**.

### Verified live Autotask Services native field schema

A governed Jason `service.entity.fields.describe` read of `Services` succeeded. The relevant native fields are:

| Field | Declared length | Purpose/limitation |
| --- | ---: | --- |
| `name` | 150 | Required Service display name |
| `description` | 400 | Optional service description |
| `manufacturerServiceProvider` | 100 | Optional provider identity; ensure actual correct source |
| `manufacturerServiceProviderProductNumber` | 50 | Optional provider-associated part number, not the general short name |
| `catalogNumberPartNumber` | 50 | Optional catalog/part identifier; semantics must be verified |
| `sku` | 50 | Optional SKU |
| `invoiceDescription` | 1,000 | Separate field; **not being edited or analyzed for invoicing now** |
| `externalID`, `internalID` | 50 each | Optional native identifiers; do not repurpose without verification |

The live schema also includes `vendorCompanyID`, `billingCodeID`, `unitCost`, `unitPrice` and `periodType`. Their accurate billing/contract semantics are **not** established by this name-design step. Search by exact names `RMM` and `EDR` returned no match; **this is not evidence the catalog lacks relevant Services**, because alternative display names and match behavior are not exhaustively established.

### Proposed category-specific display-name rules

1. **Managed IT services delivered by AOT:** `Service Function + Coverage or Tier (only where meaningful)`. Example `Managed Endpoint Monitoring` for an offering delivered using **Datto RMM**; example `Endpoint Detection & Response` for a defined EDR offering using **Datto EDR**. These are illustrations, not proof that the offerings are currently contracted/sold as separate billable Services.
2. **Resold vendor licenses and subscriptions where the named plan itself matters:** `Vendor + Product + Edition/Plan`, such as `Microsoft 365 Business Premium`; preserve the exact plan tier when needed to distinguish licensing entitlements.
3. **Underlying vendor/platform versus AOT offering:** Do not automatically rename a managed service every time its monitoring/security tool changes. Record a verified vendor/service provider and identifiers in suitable native fields, and describe coverage in `description`. When a vendor-specific SKU, licensing entitlement or technical dependency makes brand identity material, including it in the Service display name may be justified after review.
4. **Units are not assumed from a name:** Per-user, per-device, per-license, recurring period, inclusions, coverage and contract applicability require separate authoritative evidence. Do not automatically invent standalone RMM/EDR charges if services are contracted as bundle components.
5. **Keep it concise and portable:** Never force an arbitrary part number into a short name or truncate data; validate actual mapped destination field lengths before approving corrections. A long narrative is not required in a name when `description` and the proper native vendor/identifier fields exist.
6. **Preserve legacy records:** No automatic mass rename, deletion, record creation, change to billing, contract, invoice description or production integration. Propose a small pilot of verified IT Services for separate exact-plan approval only after Owner accepts the naming principle.

**Owner decision requested:** Is the dual-category principle acceptable—**function/coverage-first for AOT managed services; vendor/product/plan for specific resold subscriptions**? No mutations or bulk action follow merely from an affirmative naming decision.

## 10. IT-MSA catalog family and nontechnical searchability — proposed Owner decision (2026-11-05)

**Owner context:** `IT-MSA` is AOT's intentional recognizable grouping prefix for offerings belonging to its IT managed service agreement family. Both sales and nontechnical staff must be able to find the intended item and distinguish Products from Services without relying on product-specific technical acronyms. The prefix is a business taxonomy and usability signal, **not** automatically a contract assignment or billing authorization.

### Bounded live read evidence

Through authorized Jason `service.entity.search` with a bounded `beginsWith` name filter, the initial page returned **12 IT-MSA Services** and **12 IT-MSA Products**. Both pages reached the requested limit, so **full IT-MSA population is not established**. One bounded `IT-MSA` ServiceBundles prefix query returned zero matching bundle names, which does not establish that no bundles exist under other names.

Examples observed:
- **Service** `IT-MSA-Datto EDR` — active, provider/service description present.
- **Service** `IT-MSA-User Support  8-6 M-F` — active.
- **Service** `IT-MSA-Block Labor Hours` — active.
- **Product** `IT-MSA-Block Labor Hours` — inactive.
- **Product and Service** `IT-MSA-BSNBPP` — both active. Identical/similar names across different Autotask entity types require careful selection and historical-dependency checks; no evidence yet establishes that the underlying entries are erroneous duplicates.

### Draft recommendation for owner review — no rename or change authority

1. **Keep the `IT-MSA` family prefix** for services and genuine products specifically included in the AOT IT managed-service offering; standardize punctuation/spacing progressively on new or separately approved records. Do not blanket-prefix independent licenses or ad hoc hardware simply because it is IT-related.
2. Prefer short *nontechnical* names after the family prefix that state the purchasable function/coverage, for example: `IT-MSA - Managed Endpoint Monitoring`, `IT-MSA - Endpoint Detection and Response`, `IT-MSA - Endpoint Cloud Backup`, `IT-MSA - User Support 8am-6pm`. These are illustrative future names, not corrections or an assertion of how individual items are contracted. Product vendor/service provider names (e.g. Datto RMM, Datto EDR) should appear in the native provider field/description when accurate, and in the catalog name only when that identity distinguishes the offering.
3. For vendor subscriptions sold specifically within IT-MSA, use `IT-MSA - Vendor Product Plan` when customers/sales need to distinguish entitlements; subscriptions sold outside IT-MSA should follow their appropriate independent family, not receive a misleading IT-MSA prefix.
4. **Use native Autotask structure in addition to prefix:** Product Category for applicable Products, governed Service billing codes for Services, and native ServiceBundles only for meaningful packaged Service components sold together (not simply to create a visual folder). Confirm those native category and billing-code values before proposing reclassification. The current Services field schema has `billingCodeID` but no general-purpose `productCategory`.
5. Define a sales-facing catalog guide or validated filters distinguishing **Product vs Service vs Service Bundle**, with approved descriptive keywords/aliases as permitted by native UX. A text prefix alone does not prove selection safety where similar records exist in multiple entity types.
6. Validate field portability to mapped downstream systems before approving any name; avoid forcing manufacturer part numbers into names, inventing identifiers, duplicating billing or renaming historical records without exact authorization.
7. Keep AOT's vendor-specific, nontechnical and bundled offerings clearly separated; do not infer contract/billing meaning from `IT-MSA` alone. **No catalog mutation, invoice work, contract change, bulk cleanup, or production modification** is authorized by this proposal.

**One Owner decision requested:** Adopt **`IT-MSA` as an intentional family/search prefix, with plain-language functional names and native record-type/category differentiation** for the eventual limited IT Product/Service naming pilot?

## 11. Controlled catalog inactivation and historical preservation — draft review gate (2026-11-05)

**Owner direction:** Some legacy IT-MSA Products and Services may be inappropriate, redundant, incorrectly classified or obsolete because their original setup preceded a settled catalog standard. Jason should help identify candidates and recommend safe corrections, **one reviewed record or tightly bound pair at a time** until the Owner approves an exact larger correction plan. The approved agreement already requires preferred-record selection, relationship preservation, no unsafe deletion and human approval of exact changes.

### Review dispositions (proposed, not yet adopted)

1. **Keep active:** The record represents an approved, currently needed offering or is required by an active downstream workflow.
2. **Standardize:** The record is legitimately used but has incomplete, ambiguous or nonportable catalog data. Propose correction only after validating its dependencies and the exact fields.
3. **Inactivate candidate:** The record appears duplicate/obsolete/misclassified; select a validated preferred alternative and demonstrate it is not needed for current contracts, recurring billing, quote pipelines, open orders, inventory movement, existing integrations or technician/sales workflows. Historical references must remain intact and native platform behavior must be checked before any inactivation.
4. **Hold / investigate:** Evidence is conflicting, a relationship is inaccessible, or stock/financial/contract impact is uncertain. No inactivation while uncertainty affects safe operation.

**Gates before an inactivation may be authorized:** exact Product or Service ID, current state, evidence-based reason, correct record type, complete relevant current dependency audit, validated preferred replacement, observed native inactivation effects, a documented rollback/reactivation path, separate exact Owner approval, governed execution, and provider readback verification. No deletion, billing/contract modifications or bulk action is implied by a candidate classification. Vendor costs and customer-specific financial terms are preserved.

### First bounded case: IT-MSA-BSNBPP versus IT-MSA-BSNBPP (OPTIONAL)

On 2026-11-05, Jason used authorized governed `service.product.read`, `service.service.read`, `service.ticket.charge.search`, `service.purchase.order.item.search`, `service.entity.search`, and `service.entity.read` operations. The observations were:

| Record | ID | Current state | Observed fact |
| --- | ---: | --- | --- |
| Product `IT-MSA-BSNBPP` | 29683080 | Active | Description and prices unset. One InventoryItem reference ID 178, location 1, `quantityOnHand=1`, zero picked/reserved/on order. |
| Service `IT-MSA-BSNBPP` | 31 | Active | Has a substantive service description and configured unit cost/price; no complete active contract usage check performed. |
| Product `IT-MSA-BSNBPP (OPTIONAL)` | 29683081 | Active | Description and prices unset. One InventoryItem reference ID 179, location 1, `quantityOnHand=1`, zero picked/reserved/on order. |
| Service `IT-MSA-BSNBPP (OPTIONAL)` | 32 | Inactive | Service description present; existing inactive state is not evidence the corresponding Product can safely be retired. |

The two Product IDs returned **zero matches** from bounded TicketCharges, PurchaseOrderItems and QuoteItems searches; this is *only absence of matches in those queried surfaces*, not proof of no complete historical or current references. Both Products have stock entries with quantity 1, which may be an inventory placeholder or a real balance; determine this before any inactivation. Also verify open inventory/quote/procurement dependencies, workflow references, integrations, current Contract/Service assignments and revenue impact under the separately authorized client-scope rules. ContractServices governed-read coverage remains a known gap and must not be bypassed.

**Initial disposition: All four records are HOLD / INVESTIGATE for inactivation purposes.** The two Product records are reasonable *candidates for detailed classification*, not approved inactivations. Product and Service entity types are different and identical names do not prove they are redundant.

**Approval boundary:** Owner discussion of the disposition model does not authorize changing `isActive` or any other field. Perform the next read-only check on a single bounded case; present exact safe correction plan and obtain separate authorization before any live change.

## 12. Immediate next authorized work

- Preserve the approved agreement and this plan in repository review without touching production.
- Validate the precise governed search argument and pagination schema through allowed metadata/read operations.
- Prepare and perform bounded read-only inventory extraction, with evidence collection and recovery, only through approved existing governed read paths.
- Report confirmed counts, relationship gaps, and proposed correction-plan boundaries; do **not** claim the six-phase workstream or Phase 1 complete prematurely.
- Reserve catalog mutations, contract/billing adjustments, new capability activation and deployment for their separate approvals.

**Current status:** Phase 1 remains **in discovery; not inventoried or accepted**. The bounded IT-MSA reads above are examples, not a verified full-population count or complete dependency audit.