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

## 7. Client-friendly invoices and monthly device/subscription quantities (Owner requirement, 2026-11-05)

**Owner intent:** The customer invoice should explain, without overwhelming detail, what was supplied, what it covers, the month or service period, quantity and pricing. Each month, use authoritative device and subscription data and existing native capabilities of Autotask PSA, QuickBooks Online (QBO), and the source platforms. This is a design/acceptance constraint for Product/Service standardization and downstream Phase 6 reconciliation, **not approval for catalog changes, contract amendments, invoice creation/posting, account mapping changes, or production deployment**. Approved Agreement Version 1.4 remains unchanged.

### Client-facing invoice design (proposed; one approved pilot before expansion)

- Use plain-English Product and Service names, not internal codes or unexplained acronyms. Make each line clearly identify coverage, billing month, quantity/unit and agreed price; use concise descriptions rather than long feature lists.
- Group appropriately under a recognizable service or contract bundle where native Autotask invoicing supports it and the grouped presentation matches customer terms. Do not combine items in a way that obscures different rates, taxes, units, billing commitments or price adjustments.
- Keep the invoice short. Do **not** print every device hostname, serial number, account name or subscription user on it by default. Make a separate access-controlled device/license detail schedule or portal report available to the authorized client contact for transparency.
- Separate an internal stable catalog name/identifier and manufacturer part number/SKU from the **invoice-facing description**. Validate the actually rendered QBO invoice for line grouping, text clarity, mapping uniqueness and absence of truncation.
- Illustrative, not real charges: "Managed IT Support - Workstations | Nov 2026 | 25 devices"; "Microsoft 365 Business Premium | Nov 2026 | 18 users"; "Managed Endpoint Backup | Nov 2026 | 7 devices". Actual prices, units, discounts, minimums and proration must come from approved client terms.

### Monthly evidence, authority and reconciliation

1. **Autotask Contracts and Services** (plus applicable agreements) govern the customer's billable products/services, approved rates, billing terms, minimums and quantity methodology. **QBO** is AOT's accounting/invoicing platform. Endpoint/vendor telemetry is observation, not independent authority to increase billing.
2. For each client/service each month, obtain covered device counts from the appropriate authorized sources (e.g., Datto RMM for covered managed devices and the appropriate backup/security product for protection-specific coverage). Corroborate with Autotask configuration/asset information as applicable; exclude inactive, duplicate, retired and noncovered units according to separately agreed eligibility rules.
3. Retrieve license/subscription information from the authoritative vendor tenant, vendor portal or reseller source. Distinguish purchased/subscribed, assigned/active, contracted/billable and actually billed units. Do not assume these counts are interchangeable.
4. Record a dated internal monthly snapshot per client/product: source, retrieval time, coverage rule, count, contract baseline, billing period, additions/removals, minimum/commitment, proration, evidence, discrepancies and exception owner.
5. Compare each source observation with the Autotask contract/recurring-service quantity, posted billing items and QBO invoice. Detect missing/duplicate charges, quantity drift, unexpected rates and ambiguous source identity. Do not silently modify billable quantities or financial data; unresolved discrepancies route for governed review.
6. **Native first:** evaluate Autotask Recurring Service Contracts, ContractServiceUnit effective-date quantities, invoice templates, approve/post flow, and native platform integrations; then use the documented Smart Accounting Hub Autotask-to-QBO invoice sync and billing-code-to-QBO-Item mappings where AOT has them enabled and approved. Jason should correlate/summarize evidence and propose exceptions, not replace existing accurate billing engines.
7. Test one specifically approved client scenario with a safe preview or controlled sync, checking client-visible invoice text, quantity/rate/total, proration/taxes, item ID mappings, duplicate prevention and actual QBO readback. Any action that could create, post, send or change an accounting record requires separate exact authorization.

### Platform documentation and current limitation

- Autotask 2026.6 describes Smart Accounting Hub billing-code-to-QBO item mapping and event-driven invoice synchronization after invoice descriptions, taxes and IDs are complete. This is a **documented platform capability, not proof that AOT has configured or accepted it**: https://psa.datto.com/releasenotes/Content/ENGLISH/2026.6ReleaseNotes.htm
- Autotask ContractServiceUnits document per-period effective-dated service quantities: https://psa.datto.com/help/DeveloperHelp/Content/APIs/REST/Entities/RecurringSerContractEntityRelation.htm
- QBO supports customer-visible item descriptions, quantities/rates, invoice layout customization and attachments: https://quickbooks.intuit.com/learn-support/en-us/help-article/invoicing/create-invoices-quickbooks-online/L7gSzvCld_US_en_US
- Jason currently offers governed read-only Autotask billing/invoice and QBO invoice search capabilities; **this does not establish operational synchronization, source reconciliation, or approval for invoice mutations**.

**Acceptance gate:** A controlled authorized pilot must yield a short, understandable client invoice and separately traceable monthly reconciliation record; quantities, rates, tax and final QBO entries agree with the approved source of truth; data or privacy exceptions block the affected automatic progression. No bulk action until the Owner approves the process after pilot verification.

## 8. Immediate next authorized work

- Preserve the approved agreement and this plan in repository review without touching production.
- Validate the precise governed search argument and pagination schema through allowed metadata/read operations.
- Prepare and perform bounded read-only inventory extraction, with evidence collection and recovery, only through approved existing governed read paths.
- Report confirmed counts, relationship gaps, and proposed correction-plan boundaries; do **not** claim the six-phase workstream or Phase 1 complete prematurely.
- Reserve catalog mutations, contract/billing adjustments, new capability activation and deployment for their separate approvals.

**Current status:** Phase 1 is **planned, not inventoried or accepted**. This document contains no observed live record-count or full-population result.