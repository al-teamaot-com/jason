# AOT managed Services and Bundles — Phase 3/4 governed pilot preparation
**State:** source-only review plan, NOT approved for provider mutation, financial changes, customer contract changes, or deployment.  
**Prepared:** 2026-11-17.  
**Authority:** Autotask Inventory Cleanup Agreement v1.4, approved 2026-11-05, Phases 3–4; Project Jason Governance Handbook; AOT Managed Services Catalog Blueprint v1 (2026-11-16).  
**Release lane:** Catalog-only Service identity and Owner exact-grant correction, developed in PRs #2515 and #2522; read-only catalog admission in #2528. The separate scoped dual-image promotion implementation is in development, not accepted or deployed as of this preparation.

## Source-of-truth and preservation
- The Nov. 16 blueprint records agreed service **coverage**, but its proposed Autotask record types, internal identifiers, allocation methodology, storage allowances, and invoice behavior are **not** approved operational facts. Approved selling prices and some support/retention boundaries are missing.
- Phase 3 standardizes Services; Phase 4 builds native Service Bundles from validated underlying Services. Both require an **exact record-level plan**, applicable Owner approval, provider write/readback and dependency verification. Approval of the governing agreement alone does not authorize writes.
- Do not rename, deactivate or overwrite a legacy Service or Bundle just because a new AOT-MSA name looks similar. Preserve current contracts, invoicing, histories and financial fields; use candidate exceptions for unverifiable costs or duplicated functionality.
- Service Bundles and Autotask per-device/per-contact Billing Products are **not interchangeable**. Do not assume Integrated Customer Billing can map Service Bundles or that included components automatically roll up to a billing-product quantity. Verify native behavior before contract activation. Never double-bill a component already included in a package.

## Verified live catalog read, 2026-11-17
**Provider:** Jason governed Autotask read capabilities `service.service.search`, `service.service.bundle.search`, and `service.service.bundle.read`, no mutation.
- Services: **120 distinct IDs**, 101 active and 19 inactive. Read via first 100 rows through ID 158 and remaining 20 rows through ID 178 using `after_resource_id`; 120/120 unique across these two pages. Counts are for the currently accessible population, not a claim about hidden or inaccessible records. No exact `AOT-MSA`-named Service found (name query correlation `corr_mcp_526645a586d7450facf6dbb0d7c1df14`).
- Service Bundles: **4 active**, IDs 1–4; `AOT IT Essentials - Workstation` (1), `AOT IT Essentials - Server` (2), `AOT IT Secure – Workstations` (3), `AOT IT Secure – Server` (4). No `AOT-MSA`-named Bundle found (name query correlation `corr_mcp_d67de0d83a554e97ae1137a8203ce15c`).
- Existing Bundle 1 was separately read and verified, including its old description and pricing. None of the four current Bundles is authorization to change its composition.

## Existing underlying Services — candidate reuse, NOT equivalence approval
| Function | Existing Autotask IDs / names | Verification before reusing |
| --- | --- | --- |
| Datto RMM | 133 — `IT-MSA-Datto RMM`; 7 — `Server Monitoring` | Scope and server vs endpoint coverage, no duplicate labor |
| EDR/AV | 48 — `IT-MSA-Datto EDR` | AV and EDR coverage; cost basis; no double count of K365 suite |
| DNS protection | 50 — `IT-MSA-DNS Filter` | Existing vendor billing unit is per user; endpoint allocation remains open |
| RocketCyber | 84 — `IT-MSA-RocketCyber`; 85 — `IT-MSA-RocketCyber (SIEM)` | Potential functional overlap, not automatically duplicates |
| VulScan | 117 — `IT-MSA-AOT365 VulScan` | Site entitlement vs per-device bundle; internal/external targets, external scan capacity |
| DEB user documents | 129 — `IT-MSA-Backup Cloud storage (User Docs)`; 135 — `IT-MSA-Datto Endpoint Backup for PCs` | Scope/retention, no individual included-service invoice charge |
| DEB full image | 128 — `IT-MSA-Backup Cloud storage (Full Hard drive)`; 27 — `IT-MSA-Datto Endpoint Backup` | Workstation/server variants, full-image restore definition; BCDR excluded |
| SaaS Protection | 136 — `IT-MSA-SaaS Protection`; 79 — `IT-MSA-Office 365 Backup` | Same vs different covered Microsoft 365 workloads and billing |
| Security awareness | 82 — `IT-MSA-BullPhish ID` | Training and phishing-test scope |
| Credential exposure | 46 — `IT-MSA-Dark Web ID` | Scope and per-user cost allocation |
| Email security | 166 — `IT-MSA-INKY Std.` | **Not proven equivalent to the agreed INKY Advanced**; do not silently reuse |
| Support | 14 — `IT-MSA-User Support  8-6 M-F`; 42 — `IT-MSA-Company Support  8-6 M-F`; 89 — `IT-MSA-Server Support`; 165 — `AOT IT Essentials – User Support` | Confirm business-hours remote/onsite terms and other contract dependencies |
| Earlier package-like Services | 104 — `IT-MSA-AOT365 Endpoint Express`; 115 — `IT-MSA-AOT365 Endpoint Pro`; 116 — `IT-MSA-AOT365 User` | Names, prices and scopes pre-date new agreed AOT-MSA design; **do not rename or reprice without exact review** |
| Storage | 28 — `IT-MSA-Backup online storage` (1 TB legacy service) | Not established as per-excess-GB usage charge |
| M365 administration | 102 — `IT-MSA-O365 user mgmt Month` | Scope differs from a full Managed User bundle |

**Known gaps to verify/create as distinct inactive records only when approved:** INKY Advanced (legacy record is Std.), SaaS Alerts, Datto Backup for Microsoft Entra ID, any missing server-specific full-image/RocketCyber/VulScan or business-hours onsite support record, and an excess-backup-GB **monthly** Service. A matching name is not evidence of matching scope or licensed unit.

## Agreed commercial offerings; identifiers and billing mechanism are still PILOT proposals
| Offering / exact proposed internal ID | Agreed coverage summary | Proposed billing mechanism; approval state |
| --- | --- | --- |
| Managed Endpoint Essentials — `AOT-MSA-END-ESS` | Workstation RMM/patching, EDR+AV, DNSFilter, DEB user documents, unlimited business-hours remote support; onsite extra | Per Device Billing Product proposed, not yet validated |
| Managed Endpoint Pro — `AOT-MSA-END-PRO` | Workstation RMM, EDR+AV, DNSFilter, full-image online backup, RocketCyber, VulScan internal/external, unlimited business-hours remote/onsite | Per Device Billing Product proposed |
| Managed Endpoint Pro Low Use — `AOT-MSA-END-LOW` | Pro-class protection and support for a specially approved low-use/kiosk workstation | Per Device Billing Product proposed; eligibility/discount TBD |
| Managed User — `AOT-MSA-USER` | INKY Advanced, SaaS Alerts, BullPhish ID, Dark Web ID, SaaS Protection, Entra configuration backup and routine Microsoft 365 administration | Per Contact Billing Product proposed, count eligible protected user once |
| Managed Server Pro — `AOT-MSA-SRV-PRO` | Server RMM, EDR+AV, RocketCyber, DEB full image, internal VulScan of covered server; business-hours remote/onsite, BCDR separate | Per Device Billing Product proposed; server workload eligibility requires validation |
| Additional Backup Storage — `AOT-MSA-BKP-GB` | Approved overage above customer-pooled DEB allowance (not an included storage fee) | Monthly Service, excess GB quantity; rate and allowance NOT approved |

Customer-visible names should use `AOT-MSA – ...`, but are **not yet created**. Avoid activating Billing Products or attaching any contract lines before native invoice, pricing, quantities and tax/accounting tests.

## Proposed new native Bundle pilot (inactive only, after validated Services and exact approval)
- `AOT-MSA – Endpoint Essentials Components`: RMM/patching, EDR+AV, DNS protection, documents backup and business-hours remote support.
- `AOT-MSA – Endpoint Pro Components`: RMM/patching, EDR+AV, DNS protection, full image, RocketCyber, internal/external VulScan and business-hours remote+onsite support.
- `AOT-MSA – Managed User Components`: INKY Advanced, SaaS Alerts, BullPhish ID, Dark Web ID, SaaS Protection, Entra backup and routine M365 admin.
- `AOT-MSA – Server Pro Components`: server RMM/patching, EDR+AV, RocketCyber, full-image online backup, internal VulScan and business-hours remote+onsite support.

**Crucial:** These are proposed native catalog-bundle composition tests, not yet billable packages. Confirm the native Service Bundle child-line data model, quantity/price behavior and invoice compatibility first; the ultimate commercial package may remain a per-device/per-contact Billing Product with separate internal component mapping. No dual charging.

## Design details to carry through pilot
- Business hours: Mon–Fri, 8 AM–6 PM Eastern, excluding AOT-observed holidays. Projects, after-hours work, and BCDR/failover are separate.
- One Managed User per eligible protected person, even across multiple workstations. An exception is required for standalone Managed User.
- Proposed server quantity: bill eligible server workload; hypervisor with N server VMs bills N, with host covered at no additional server fee; VM leaves count only after >30 consecutive offline days. All needs live rule validation.
- VulScan subscription: 50 sites on cited November invoice; scan targets and extra external IP-scans are separate license/capacity concepts. Do not equate one protected Pro device with one VulScan site license.
- Candidate backup allowance only: 100 GB Essentials, 500 GB Pro, 1,000 GB/server pooled per customer. No commercial activation without Owner's allowance and excess-price approval, current policy/capacity read, usage freshness, units and rounding/retention rules.
- K365 suite costs should be allocated only once; internal component allocations are not extra vendor charges. Existing customer-specific contract rates stay unchanged.

## Governed shortest execution path
1. **Release prerequisite (parallel engineering, separate worktree):** Complete the existing scoped two-image Catalog runtime/MCP promotion transaction, exact-source/rollback proof, freeze/host/PMv4/Ticket Core noninterference and audited Owner approval. Do not reimplement on this branch.
2. **Read-only inventory acceptance:** Reconfirm 120 accessible Services, 4 Bundles, existing IDs, duplicates/dependencies and current permission posture immediately before mutations. Any drift becomes an exception for the exact plan; do not assume prior historical IDs are globally stable.
3. **First exact no-billing acceptance plan:** Specify one unique inactive `AOT-MSA – Catalog Write Acceptance` Service name, exact description, all native fields and financial defaults, no contract assignment, no notifications, before-read, recovery disposition and post-write readback. Obtain separate authorized phase/action approval. Jason uses **its own** Autotask API service identity; human Entra Owner authorizes and is audited; no Autotask impersonation on the four catalog Service/Bundle create/update operations.
4. **Service phase:** For every reusable candidate, verify exact semantics and contract dependencies before matching; for every true missing component, prepare the approved create plan with exact fields, vendor/licensing unit, evidence-backed cost and price policy or documented exception. Execute only approved nonfinancial/financial operations, read back each.
5. **Bundle phase:** Compose only from validated child Services; verify exact membership, quantities, pricing model, billing-code/tax behavior, native readback and no invoice duplication. Do not change/retire legacy Bundle IDs 1–4 without separate exact authorization and dependency proof.
6. **Commercial pilot:** Validate Device/Contact Billing Products vs native Bundles, 2-tier mixed customer, user across devices, VM eligibility, storage under/over, missing usage exception, VulScan entitlement, invoice rendering and account/tax mappings. Approve selling prices and customer-specific terms separately, then activate selected pilot contracts only under exact approved plans.

## Proof / acceptance checklist
- [x] Provider-backed baseline (120 Services, 4 Bundles, zero `AOT-MSA` names) as of 2026-11-17
- [x] Source-only record mapping against November 16 blueprint; no production mutation
- [ ] Scoped runtime/MCP production release, authenticated exact Owner approval, rollback and unchanged Ticket Core verified
- [ ] Actual inactive no-billing Service create/readback under Jason's independent Autotask identity, audit and precise Owner grant
- [ ] Complete approved Phase 3 review population and verified Services
- [ ] Approved native Service Bundle create/readback and composition
- [ ] No duplicate invoice charges, correct usage/quantity calculation and price authorization
- [ ] Selected contract/invoice pilot, financial verification and acceptance

**Do not promote this design document as proof of provider catalog creation.** The parent workstream remains incomplete until those operational checks pass.
