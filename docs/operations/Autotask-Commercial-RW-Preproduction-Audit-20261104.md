# Autotask commercial RW access — read-only audit and preproduction gates (2026-11-04)

**Status:** Core commercial RW provider-backed GET acceptance passed; scope/checkbox and billing-join negatives outstanding. **Not production eligible.**  
**Related:** #200 vendor-cost/client-billing reconciliation, #403 governed billing operations, #435 contract intelligence, #2147 invoice-read repair, #2104 technician authorization repair.

## Scope and invariants

- Reuse **existing** AOT Autotask API user **Jason ReadWrite** (Resource ID `29682930`, `jasonRW@teamaot.com`). **Do not create another API identity**.
- Existing `autotask.readonly` and `autotask.write` are deliberately separate credential contracts. Metadata seen under `autotask.readonly` does **not** establish `autotask.write` effective permissions.
- In this phase only inspect provider and Jason authority, prepare isolated code/tests, and collect non-secret evidence. **No production changes, Autotask writes, billing/price/quantity changes, contract posting, invoice posting, secret rotation, permission changes, or credential extraction**.
- Preserve `direct_provider_access=false`, exact grants, centrally governed execution, requester/client disclosure policy, immutable evidence, and the exact-SHA deployment approval gate. No unsupported provider/API route, shell credential bypass, or privilege elevation.
- Treat **configured provider permissions**, **actual provider GET authorization**, **Jason capability registry**, **requester execution grants**, **per-action approval**, and **record-specific verification** as separate assertions. None substitutes for another.

## Verified observations

### Provider identity and assignments

Live Autotask browser read on 2026-11-04:
- Jason ReadWrite, Resource ID `29682930`, active.
- Assigned security level: **AOT - API User (Integration)** (security level ID `27`).
- All configured visible LOB choices are in **Associated**; **Not Associated** is empty:
  - `18`: IT/Helpdesk > Cabling
  - `17`: IT/Helpdesk > IT Services
  - `19`: IT/Helpdesk > Network Install
  - `20`: IT/Helpdesk > Security
- **Not yet proven:** selected state of **Resource can view items with no assigned Line of Business**. Browser text extraction exposes the label but not the checkbox value. Must inspect directly or prove by RW GET on a known unassigned-LOB record.
- Historic provider-backed write acceptance attributes mutation to Resource `29682930` (`docs/sessions/Jason-Autonomous-Execution-Production-Acceptance-2026-09-25.md`); this is historical identity evidence, not a fresh commercial RW read.

### Security level

The live Security Level 27 editor showed these **selected dropdown permissions**:
- Contracts: View **All**, Add **Yes**, visibility **Full**, Approve & Post **All**, Invoice **All**.
- CRM: all customer/vendor/prospect company classes visible; products/vendors/quotes etc. broad create/edit permissions.
- Inventory: Inventory Locations, Items, Products, Purchase Orders all View **All**, Add **Yes**, Edit **All**, Delete **All**.
- Opportunities & Quotes: View **All**, Add **Yes**, Edit **All**, Delete **All**.
- Devices & Subscriptions: View **All**, Add **Yes**, Edit **All**, Delete **All**.

**Visual screenshot evidence (2026-11-04):** All six Contracts checkboxes are **checked**, including modifying contract internal costs, modifying Service/Bundle on contract charges, viewing posted billing items, creating invoices from ticket/won quote wizard, invoice history/export/payments and accessing Bulk Service Updater. The Resource HR internal-cost-section checkbox in **Other** is also checked, and the overall resource-visibility limiter is unchecked. **Still not visually verified:** the separate `Can view internal cost data (excludes New/Edit Resource page)`, `Can view sensitive Charge data`, and `Can login to Web Services API` checkboxes, plus the API-user `Resource can view items with no assigned Line of Business` checkbox. The screenshot does not extend to those controls. The profile is broadly permissive; do **not** treat that as authorization for autonomous money-moving or obligation-changing operations. Source: `evidence/Autotask-RW-Security-Level-Checkbox-Visual-20261104.json`.

### Live Jason read and authorization (READ credential only)

- MCP service reports `status=ok`, `mode=governed-read-plus-actions`, `governed_execution=central-orchestrator`.
- `service.entity.describe` under the governed **read** connection showed `userAccessForQuery=All` for `Products`, `Services`, `ProductVendors`, and `ServiceBundles`.
- Under that same **read** connection, `ContractServices`, `BillingItems`, and `Invoices` showed `userAccessForQuery=None`; `ContractServiceAdjustments` showed `canQuery=false` and `userAccessForQuery=None`. **These restrictions must not be attributed to Jason ReadWrite without a RW credential test.**
- Governed `service.service.search` returned 100 services; 52 had nonzero unit cost in the returned sample. This proves limited observed read-field access, not total vendor-cost coverage or RW financial visibility.
- Actual contract reads included association `17` and null/unassigned association values for sampled customers; performed via the separate governed read connection.
- Catalog mutations including `service.product.create/update`, `service.service.create/update`, `service.service.bundle.create/update`, `service.purchase.order.create/update` are registered active but returned **`authority_outcome=denied` for this caller**. `service.ticket.update` separately reports `approval_required`. Do not conflate registered operations with executable grants. Do not attempt a mutation as a permission test.

### RW secret-safe preflight

- Existing tool: `tools/autotask_mutation_readiness.py` (`autotask.write`); its `ReadOnlyReadinessTransport` permits only GET and never dispatches compiled POST/PATCH.
- `--check-only` succeeded; **this does not contact Autotask or prove credentials**.
- The trusted AOT human requester binding was confirmed active in the local binding store.
- An initial **interactive shell** `--live-read` run was denied **before provider contact** by the write AppRole file ACL. This was not treated as permission to elevate the interactive account or copy credentials. A second run of the **same unchanged GET-only tool** inside the existing authorized `jason-runtime` service context **passed** at `2026-11-04T17:28:12.824092+00:00`: 4/4 request-bound Ticket/TicketNote preflights, 12 provider GETs, unique trusted requester binding, no provider writes, no credentials printed/persisted. Execution used the normal service user, existing mounted OpenBao AppRole and original source streamed into process memory; no container source, installed service, or production configuration was modified.
- In the existing non-production working copy, `python3 -m pytest -q tools/tests/test_autotask_mutation_readiness.py` passed **5 tests**; `python3 -m pytest -q implementation/connectors/tests/test_autotask_mutation_connector.py` passed **11 tests**.
- The current checked-out `/home/al/projects/jason` worktree contains **unrelated uncommitted procurement changes**. Do not modify or reset it; prepare work in an isolated branch/worktree.

## Exact remaining preproduction acceptance matrix

| Gate | Evidence required | Current disposition |
|---|---|---|
| RW credential identity | Secure runner obtains `autotask.write` through its existing approved OpenBao AppRole; provider-backed identity evidence matches Jason ReadWrite `29682930` without disclosing secret | **PASS in authorized service context**; original interactive-shell denial is resolved |
| RW provider GET authorization | Fixed allowlisted, GET-only compiled connector reads in an authorized service context (no new standing capability) | **PASS**: 32 GET calls, entity metadata and bounded records for core commercial objects; no writes |
| LOB consistency | Verify `17/18/19/20` assignment plus record scope, including null LOB | Assignments pass; **16 unassigned-LOB contracts returned** by RW; per-LOB record coverage not fully proved |
| Cost and pricing | Confirm visible cost values and independently confirm UI checkbox selections | **RW nonzero-cost fields verified** for Products, Services, ProductVendors, ServiceBundles, BillingItems; **contract internal-cost mutation checkbox visually checked**, standalone general cost-visibility checkbox still off-screen |
| Commercial coverage | Validate Products, ProductVendors, Services, ServiceBundles, POs, contracts/**ContractServices**, BillingItems, Invoices and exact billing joins | **Core seven entity reads pass**; ContractServices approved record-read route and exact joins not tested |
| Permission divergence | Compare effective RW metadata and records with security level and separate read-only credential | **Verified**: RW Contracts and BillingItems `Restricted` (both readable), RW Invoices `All` and readable while existing RO account is denied; further record-scope negatives pending |
| Jason execution grant | Registry state + exact matched principal/grant, organization/client, execution plan/approval policy. Negative tests ensure catalog/billing writes denied until separately approved | **Caller denial confirmed**; full grant matrix pending |
| Financial-control gates | Deterministic read-only reconciliation; write/contract quantity/price/invoice/posting must fail closed without separate human-governed authority | No financial writes attempted |
| Release hygiene | Isolated preprod branch; CI, client/LOB negative tests, leakage tests, provider-backed read acceptance and rollback evidence | **Draft documentation PR #2308**; no release eligible |

## Remaining acceptance path

1. Under a **reviewed, preproduction-only, allowlisted, GET-only** provider verification route (not ad-hoc direct HTTP), obtain `entityInformation` and bounded record/field proofs for the commercial objects above. A missing approved route is a development task, not permission to bypass Jason's connector boundary.
2. Record sanitized operation, entity, requested field class, provider result, LOB association and correlation/evidence hash; never persist raw credentials or sensitive billing values.
3. Independently confirm the selected state of the RW account's **unassigned-LOB** setting and internal-cost security-level checkboxes; do not infer checkbox state from plain extracted labels.
4. For `Restricted`, run approved per-client/LOB disclosure negatives before claiming all-record access. For `None`, fail closed and record the exact denied entity/operation. No live permission changes without explicit approval.
5. Complete provider-backed negative tests under unauthorized principals, negative client context, denial of finance mutation, and safe pagination. Then attach CI/preproduction output and review existing workstream #2147 (invoice read HTTP 500) to avoid duplicate fixes. 
6. Present an exact production candidate/rollback SHA **only after** full source and preproduction acceptance. **Do not deploy or lift the production freeze** without separate owner approval.

## 2026-11-04 supplemental live evidence

The authenticated provider-backed runtime observations are preserved as a sanitized [machine-readable evidence record](evidence/Autotask-RW-Commercial-GET-Acceptance-20261104.json). The test-only diagnostic reused Autotask's existing typed, compiled GET read operations and `autotask.write` inside the authorized service context; it did not create a new production read route, broaden Jason grants, or persist customer records.

| Provider entity | Actual RW read | Returned records | RW query access |
|---|---|---:|---|
| Products | PASS | 50 | All |
| Services | PASS | 50 | All |
| ProductVendors | PASS | 50 | All |
| ServiceBundles | PASS | 4 | All |
| Contracts | PASS | 50 | Restricted |
| BillingItems | PASS | 50 | Restricted |
| Invoices | PASS | 50 | All |
| ContractServices | Metadata only | Not attempted (outside current approved read allowlist) | Restricted |

Cost visibility: returned nonzero cost records in Products (50/50), Services (18/50), ProductVendors (49/50), ServiceBundles (4/4), and BillingItems (5/50). Price fields were also present in Products, Services, ServiceBundles and BillingItems. The RW-protected resource read for ID `29682930` matched its known account email; this is a readback identity consistency check, not fresh token introspection.

**Operational conclusions:** Existing RW credential access for the seven queried commercial entity families is proved by actual provider records. Contract/BillingItem `Restricted` is not `None`; it must be interpreted as conditional and cannot substantiate universal cross-client record reach. The invoices endpoint is reachable and returns 50 rows under the RW identity, whereas historical `#2147` failures used a different read path/credential and must be separately root-caused. Sixteen contracts with null LOB association returned in the 50-record RW sample, functionally proving access to *some* unassigned-LOB records.

**Still outstanding:** The four literal checkbox states for API login, unassigned-LOB record visibility, standalone general internal-cost data viewing, and sensitive charge data viewing remain off-screen. All six **Contracts** checkboxes and the **Other > Resources/Users (HR) > Can view Internal Cost section on New/Edit Resource page** checkbox are independently visually verified as checked. Effective API login, cost read and null-LOB read behavior **are** also verified. A posted invoice/billing-item exact join, approved ContractServices data read, restricted-scope negative tests and a code-reviewable repeatable probe are future acceptance gates. Any potentially financial-impacting mutation still requires its separate governance and approval.

## Remaining blocker and handoff

The prior **credential-file ACL blocker is resolved** by using the intended service execution identity. The current screenshots resolve all six **Contracts** checkbox-state questions and the HR Resource cost checkbox; the four specifically listed controls remain off-screen. In addition, **scope-specific/negative record acceptance** remains outstanding, not general RW API connectivity. Obtain remaining actual checked-state evidence in an authorized GUI browser session; do not alter any checkbox for this audit.

**No provider writes or production changes were made. No deployment or merge is authorized by this evidence.**


## Visual checkbox evidence — 2026-11-04 17:42–17:43

Source: two user-provided screenshots of the live Security Level 27 edit page. Sanitized structured transcription: [Autotask-RW-Security-Level-Checkbox-Visual-20261104.json](evidence/Autotask-RW-Security-Level-Checkbox-Visual-20261104.json).

**Contracts**: View `All`; Add `Yes`; the following six checkboxes are visibly **checked**: Modify contract Internal Costs, modify Service/Bundle on contract charges, view Posted Billing Items Search, create invoices from Ticket/Won Quote Wizard, access Invoice History/Export Wizard/Payments, and access Bulk Service Updater. Contract Visibility `Full`, Can Approve & Post `All`, Can Invoice `All`.

**Other** (visible upper portion): `Can view Internal Cost section on New/Edit Resource page` is **checked**; `Limit resource availability to self, plus` is **unchecked**, with its subordinate resource limits also unchecked. `Can publish Client Portal Dashboards` is unchecked (outside the commercial audit scope). No resource or financial permissions were modified.

**Not shown** in either screenshot: selected state of the separate `Can view internal cost data (excludes New/Edit Resource page)`, `Can view sensitive Charge data`, `Can login to Web Services API`, or the API User's `Resource can view items with no assigned Line of Business`. Functional RW API GET tests substantiate working API login, nonzero costs, and some unassigned-LOB contract reads, but those tests do **not** prove the UI checkbox values.
