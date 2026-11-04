# Autotask commercial RW access — read-only audit and preproduction gates (2026-11-04)

**Status:** Partial live verification, preproduction acceptance plan. **Not production eligible.**  
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

**Not verified:** checkbox selections for `Can view internal cost data (excludes New/Edit Resource page)`, `Can view sensitive Charge data`, `Can modify contract Internal Costs`, `Can modify Service/Bundle on contract charges`, `Can access Bulk Service Updater`, and `Can login to Web Services API`. Text extraction lists labels but not checked/unchecked state. Record these via direct checked-state evidence before claiming positive permissions. The profile is broadly permissive; do **not** treat that as authorization for autonomous money-moving or obligation-changing operations.

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
- A **live** `--live-read` run using that trusted requester was denied **before provider contact** because the current operator lacks permission to read the OpenBao Autotask write AppRole role-id file. No secret values were printed, no elevated access was attempted, and no provider mutation was dispatched.
- In the existing non-production working copy, `python3 -m pytest -q tools/tests/test_autotask_mutation_readiness.py` passed **5 tests**; `python3 -m pytest -q implementation/connectors/tests/test_autotask_mutation_connector.py` passed **11 tests**.
- The current checked-out `/home/al/projects/jason` worktree contains **unrelated uncommitted procurement changes**. Do not modify or reset it; prepare work in an isolated branch/worktree.

## Exact remaining preproduction acceptance matrix

| Gate | Evidence required | Current disposition |
|---|---|---|
| RW credential identity | Secure runner obtains `autotask.write` through its existing approved OpenBao AppRole; provider-backed identity evidence matches Jason ReadWrite `29682930` without disclosing secret | **Blocked by execution identity/secret file ACL** |
| RW provider GET authorization | Using the **approved governed connector boundary**, call bounded, allowlisted GET metadata and representative read-only record paths with actual RW credentials | Not tested |
| LOB consistency | Independently verify all `17/18/19/20` mappings and read representative authorized objects in each; explicitly verify known record without LOB | Assignments pass; record-level proof outstanding |
| Cost and pricing | Confirm cost-visibility checkbox through checked-state evidence; read known nonzero unitCost/unitPrice and vendor-cost fields with RW credential; contrast same identifiers with authorized finance/UI baseline | Pending |
| Commercial coverage | Validate Products, ProductVendors, Services, ServiceBundles, Quotes/Opportunities, POs/PO Items, contracts and **ContractServices**, billing items, invoices, customer mapping and vendor/contract/billed joins | Partial reads; contract/billing chain outstanding |
| Permission divergence | Compare live RW `entityInformation` `userAccessFor*` to Security Level 27 settings, and record provider-specific exceptions including query-only or unsupported endpoints | Pending |
| Jason execution grant | Registry state + exact matched principal/grant, organization/client, execution plan/approval policy. Negative tests ensure catalog/billing writes denied until separately approved | **Caller denial confirmed**; full grant matrix pending |
| Financial-control gates | Deterministic read-only reconciliation; write/contract quantity/price/invoice/posting must fail closed without separate human-governed authority | No financial writes attempted |
| Release hygiene | Isolated preprod branch; CI, contract/LO B negative tests, data-leakage tests, provider-backed read acceptance, foundation regression, protected-main reconciliation and rollback SHA | Source planning only; no release eligible |

## Approved execution path for next RW test

1. Use the already-authorized Jason service/runtime execution context **that can resolve `autotask.write`**. Do not make the interactive operator a member of secret-access groups, copy secret files, print tokens or use `sudo` to bypass policy.
2. Invoke `tools/autotask_mutation_readiness.py --live-read` with an existing trusted AOT human principal, an expected AOT principal email, a unique correlation ID, and a new private evidence destination. Keep the script's GET-only transport invariant and verify that compiled mutations are **not** dispatched.
3. Under a **reviewed, preproduction-only, allowlisted, GET-only** provider verification route (not ad-hoc direct HTTP), obtain `entityInformation` and bounded record/field proofs for the commercial objects above. A missing approved route is a development task, not permission to bypass Jason's connector boundary.
4. Record sanitized operation, entity, requested field class, provider result, LOB association and correlation/evidence hash; never persist raw credentials or sensitive billing values.
5. Independently confirm the selected state of the RW account's **unassigned-LOB** setting and internal-cost security-level checkboxes; do not infer checkbox state from plain extracted labels.
6. If any provider permission is None/Restricted, fail closed, capture which *exact* entity/operation is denied, and prepare a minimal access-change proposal; no live permission changes without explicit authorized approval.
7. Complete provider-backed negative tests under unauthorized principals, negative client context, denial of finance mutation, and safe pagination. Then attach CI/preproduction output and review existing workstream #2147 (invoice read HTTP 500) to avoid duplicate fixes.
8. Present an exact production candidate/rollback SHA **only after** full source and preproduction acceptance. **Do not deploy or lift the production freeze** without separate owner approval.

## Blocker and handoff

**Blocker:** The currently available operator identity is denied the existing RW AppRole file, so the effective commercial API permissions of `autotask.write` are **not verified**. The safe resolution is execution in the existing authorized service context—not new credentials or privilege escalation. Human intervention is needed only if no approved service context exists or changing permission policy is genuinely necessary.

**No production changes made as part of this audit.**
