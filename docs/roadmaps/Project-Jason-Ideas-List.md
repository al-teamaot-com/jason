# Project Jason — Ideas List

> **Lightweight discovery register — documentation-only draft.** Staged on `docs/todo-category-index-20261017` on 2026-10-17. Not the production Ideas List service, not an engineering-intake queue, and **not authority to deploy anything**. The governed [TODO roadmap](./Project-Jason-TODO-and-Future-Ideas.md), [Support List](../../SUPPORT.md) and original linked GitHub sources remain authoritative for their own workflows.

**Current captured ideas:** 44 (from four explicit IDEA issues and owner-submitted Ideas List comments); **impact areas:** six; **suggested value:** 17 High, 26 Medium, 0 Low, 1 Unrated. These are *provisional editorial classifications*, not live-use metrics or a new priority order. Original submissions, dates and author provenance remain at the linked source.

## How it works

**Anyone at AOT can propose an idea in plain language.** When the governed submission capability eventually goes live, Jason should save the text, source and author automatically, suggest a single primary category and one value rating, check existing ideas/TODOs, and respond with a stable IDEA ID. Employees need not fill in a form, choose categories, supply evidence, or obtain management approval just to submit.

**Impact areas:**
- **System & Reliability:** Jason stability, system integrations, performance, architecture and dependable operation.
- **Usability & Technician Experience:** easy interfaces, useful technician tools, onboarding and less friction.
- **Client Experience & Service:** customer support quality, prevention, responsiveness and service outcomes.
- **Security & Governance:** risk reduction, privacy, approved access, compliance and safety.
- **Efficiency & Automation:** eliminate repetitive work and improve operational processes.
- **Business & Growth:** revenue assurance, cost, margin, procurement and commercial/product value.

**Potential value:** High (material prospective benefit); Medium (worthwhile, bounded benefit); Low (nice-to-have or narrow); Unrated (not enough evidence). *Value is NOT urgency, engineering priority, approval, or a P0 tag.* Confirmed existing defects belong in [SUPPORT.md](../../SUPPORT.md), not an Ideas List implementation queue.

**Lightweight status:** New → Considering → Candidate TODO → Incorporated; alternatively Parked or Rejected. These are discovery dispositions. The first import below uses **Considering** for cataloged ideas without making them eligible engineering TODOs; a GitHub issue being open is not itself an endorsement or completed review. Related ideas may be clustered while preserving their stable IDEA IDs and original attribution. Promotion requires the **existing** governed TODO review and authority; the daily discovery worker cannot admit ideas for code/release itself.

**Stable import IDs:** `IDEA-0001` … `IDEA-0044` are initial catalog IDs assigned here; do not reassign them when reordering or clustering. Any future automated `ideas.submit` implementation must import/preserve these IDs and continue from an unused identifier rather than generating duplicates. Linked original GitHub issues/comments remain the evidence records. There is **no current active `ideas.submit` capability** verified as of this audit; [#1519](https://github.com/al-teamaot-com/jason/issues/1519) governs development with production activation held behind Teams acceptance.

## At a glance

| Impact area | Ideas | Highest initial value |
| --- | ---: | ---: |
| [System & Reliability](#system-reliability) | 3 | 1 High |
| [Usability & Technician Experience](#usability-technician-experience) | 5 | 2 High |
| [Client Experience & Service](#client-experience-service) | 6 | 4 High |
| [Security & Governance](#security-governance) | 1 | 1 High |
| [Efficiency & Automation](#efficiency-automation) | 7 | 0 High |
| [Business & Growth](#business-growth) | 22 | 9 High |

## Browsable ideas by impact

Every title opens the **original suggestion**, not a new duplicate GitHub task. Long descriptions remain in source records. Potential ranks are review aids only.

### System & Reliability

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0041` | [First-class ticket queue monitor health](https://github.com/al-teamaot-com/jason/issues/1137) — Show real queue scan freshness, admission results, and stalls instead of relying on process health. | High | Considering¹ |
| `IDEA-0016` | [Copier address-book / configuration drift](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Detect meaningful device-side configuration changes and answer "what changed since this worked?" | Medium | Considering¹ |
| `IDEA-0040` | [Evaluate Paperclip for Jason's orchestration](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-6046784948) — Research an optional reusable orchestration layer; Jason remains the MSP authority and product. | Unrated | Considering |

### Usability & Technician Experience

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0003` | [First-time-fix copier assistant](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — For a copier ticket, correlate model, current errors, firmware, counters, past repairs, and known fixes to produce a short likely-cause / checks / parts-to-bring brief. | High | Considering |
| `IDEA-0039` | [Jason setup as onboarding a new employee](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5983051128) — A guided named-AI-technician onboarding that configures role, authority, communication and readiness. | High | Considering |
| `IDEA-0019` | [Copy-team knowledge mining](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Mine confirmed copier-ticket resolutions and technician notes for durable model-specific troubleshooting knowledge, then preserve validated fixes for future reuse. | Medium | Considering |
| `IDEA-0042` | [Daily urgent operations briefing in Teams](https://github.com/al-teamaot-com/jason/issues/1305) — Summarize urgent action, active handling and recently verified resolutions once daily. | Medium | Considering |
| `IDEA-0043` | [Investigate duplicate Teams ticket cards](https://github.com/al-teamaot-com/jason/issues/1306) — Trace repeated cards by ticket/lifecycle event; may belong in Support after verification. | Medium | Considering¹ |

### Client Experience & Service

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0001` | [Copier service-call prediction](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Use jam history, maintenance-kit life, service-call codes, usage, and recurring error patterns to predict likely service needs before the client calls. | High | Considering |
| `IDEA-0004` | [Repeat-problem detector](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Detect repeated service incidents on the same machine or model and flag recurring equipment problems instead of treating each ticket independently. | High | Considering |
| `IDEA-0015` | [Scan destination health monitoring](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Proactively verify critical SMB/SMTP/other scan destinations and identify likely failures caused by server migrations, certificate changes, authentication changes, DNS, or reachability. | High | Considering |
| `IDEA-0044` | [Verify VulScan ticket close-pending transitions](https://github.com/al-teamaot-com/jason/issues/1308) — Check whether ticket status actually changes after remediation; candidate Support defect. | High | Considering¹ |
| `IDEA-0018` | [Client copier dependency map](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Correlate each managed copier with the departments/users/PCs that depend on it, scan destinations, network dependencies, and business impact. | Medium | Considering |
| `IDEA-0020` | [Practical Copier Health Score](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Build a useful operational view based on reliability, consumables, maintenance, firmware, reporting freshness, service frequency, and utilization — with concrete next actions, not a decorative score. | Medium | Considering |

### Security & Governance

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0017` | [Copier security exposure review](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Identify unnecessary services, weak/legacy protocols, outdated certificates, insecure scan protocols, management exposure, and other vendor-supported security findings. | High | Considering |

### Efficiency & Automation

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0002` | [Parts prediction beyond toner](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Predict drums, maintenance kits, waste toner containers, staples, fusers, and other model-specific service parts using counters, history, and replacement intervals. | Medium | Considering |
| `IDEA-0005` | [Fleet outlier detection](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Compare like-for-like devices and flag abnormal toner consumption, jam frequency, service frequency, error rate, or utilization. | Medium | Considering |
| `IDEA-0010` | [Supply delivery verification](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Correlate toner/supply orders with exact device, serial, color/part number, current level, predicted exhaustion date, and recent replacement history to reduce duplicate/wrong shipments. | Medium | Considering |
| `IDEA-0012` | [Copier move detection](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Detect meaningful changes in IP/site/network/location/reporting context that suggest a machine was physically moved and documentation/contracts may need updating. | Medium | Considering |
| `IDEA-0013` | [New copier commissioning workflow](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Standardize onboarding: serial/model/firmware, networking, KFS registration, counters, toner, security baseline, driver/scanner/fax deployment, Autotask asset/contract, and documentation. | Medium | Considering |
| `IDEA-0014` | [Copier retirement workflow](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Capture final meters, remove from KFS/contracts, document serial/disposition, remove scan/address-book credentials where applicable, remove endpoint queues, and preserve evidence. | Medium | Considering |
| `IDEA-0036` | [Finance-platform-specific reconciliation opportunities](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Research ConnectBooster, QuickBooks Online, Autotask, GreatAmerica/other AOT finance platforms and their supported APIs/integrations for native capabilities Jason can monitor or reconcile before building custom logic. | Medium | Considering |

### Business & Growth

| IDEA ID | Suggestion / intended benefit | Potential | Stage |
| --- | --- | --- | --- |
| `IDEA-0008` | [Meter-reading QA](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Detect suspicious meter decreases, jumps, missing periods, stale readings, serial mismatches, or other anomalies before billing/reporting errors occur. | High | Considering |
| `IDEA-0009` | [Contract-to-device reconciliation](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Compare KFS/reporting devices against Autotask assets/contracts to find unbilled reporting devices, missing contracted devices, serial mismatches, moved devices, or stale assets. | High | Considering |
| `IDEA-0021` | [A/R exception management](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Identify overdue invoices, failed payments, unapplied payments, credits, duplicate balances, and cross-system balance mismatches. | High | Considering |
| `IDEA-0022` | [Payment reconciliation watchdog](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Verify that payments received through payment platforms/accounting systems are applied to the correct customer and invoice and are not left unmatched or unapplied. | High | Considering |
| `IDEA-0024` | [PSA-to-accounting invoice reconciliation](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Compare Autotask invoices against QuickBooks Online/accounting records for customer, invoice number, amount, tax, line totals, credits, payment status, and dates. | High | Considering |
| `IDEA-0026` | [Contract billing QA before invoice generation](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Validate device counts, user counts, contract quantities, included services, minimums, overages, proration, and recent operational changes before billing. | High | Considering |
| `IDEA-0027` | [Recurring revenue leakage detection](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Find active managed users/devices/services without corresponding recurring contract charges, and stale/canceled assets still being billed. | High | Considering |
| `IDEA-0030` | [Procurement-to-payment closed-loop assurance](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Trace quote, purchase, receipt, charge, invoice, payment and application; flag missing links. | High | Considering |
| `IDEA-0034` | [Billing anomaly detection](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Detect unusual invoice amounts, duplicates, missing recurring invoices, unexpected tax/credits, sudden billing drops, and unusual month-over-month changes. | High | Considering |
| `IDEA-0006` | [Device placement / right-sizing intelligence](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Match devices to client usage and placement needs. | Medium | Considering |
| `IDEA-0007` | [Lease / replacement intelligence](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Combine age, meter counts, service history, maintenance burden, consumable use, and contract context to identify machines that may be better replaced than repaired. | Medium | Considering |
| `IDEA-0011` | [Toner anomaly / leakage detection](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335) — Detect abnormal yield, repeated replacement events, or shipments that do not line up with actual device depletion and usage. | Medium | Considering |
| `IDEA-0023` | [AutoPay coverage intelligence](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Detect clients/contracts that should likely be on AutoPay but are not, failed AutoPay rules, unexpected exclusions, or invoices bypassing intended payment rules. | Medium | Considering |
| `IDEA-0025` | [Billing-contact hygiene](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Detect stale or inconsistent billing contacts/emails across Autotask, QuickBooks Online, ConnectBooster/payment systems, and other authoritative sources. | Medium | Considering |
| `IDEA-0028` | [Client/service margin intelligence](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Correlate PSA labor, procurement, contracts, and accounting revenue/cost data to identify unprofitable clients, agreements, services, or recurring support patterns. | Medium | Considering |
| `IDEA-0029` | [Vendor bill / PO / client-charge reconciliation](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Compare vendor bills against Autotask POs, receipts, client charges, and related accounting entries to find purchased items that were never billed onward or were mismatched. | Medium | Considering |
| `IDEA-0031` | [Payment-processing fee intelligence](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Measure card/ACH/payment-method costs and identify client/payment patterns that create disproportionate processing expense. | Medium | Considering |
| `IDEA-0032` | [Collections assistant](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Produce concise collections context using invoice age, amount, payment history, billing contact, disputes/open tickets, and other reasons a collection action may need review. | Medium | Considering |
| `IDEA-0033` | [Cash-flow forecasting](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Use open receivables, due dates, AutoPay status, payment history, recurring billing, vendor obligations, and known purchases to estimate expected receipts/outflows. | Medium | Considering |
| `IDEA-0035` | [Client/account master-data reconciliation](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Compare company/customer name, address, billing email, tax treatment, payment terms, IDs, and other important accounting/PSA identity data across systems. | Medium | Considering |
| `IDEA-0037` | [Financial close exception assistant](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — At month-end, identify unreconciled payments, stale A/R, vendor bills without matching purchasing evidence, unbilled charges, contract/device mismatches, and other exceptions requiring human review. | Medium | Considering |
| `IDEA-0038` | [Financial Integrity Monitor](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306) — Detect when an operational event fails to reach its expected financial result. | Medium | Considering |

¹ **Triage flags, not an execution status:** `IDEA-0043` and `IDEA-0044` describe potential existing operational faults; confirm and reconcile with the Support List instead of promoting them as feature requests. `IDEA-0041` overlaps existing ticket-worker health/reliability requirements in [#770](https://github.com/al-teamaot-com/jason/issues/770); check current scope first. These flags do not change GitHub issue status or run diagnostics.

## Clusters and existing work — preserve lineage, avoid duplicate engineering

- **Copier / Print Fleet (IDEA-0001 through IDEA-0020):** Original [20-idea cluster](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981592335). The later [predictive maintenance and repair-cost refinement](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-6024181621) belongs to the service prediction, parts, replacement and health-score ideas already recorded (**do not create a 45th duplicate**). Cross-check the existing [Copier Lifecycle / Profitability TODO #1113](https://github.com/al-teamaot-com/jason/issues/1113), [Copy Contracts #1114](https://github.com/al-teamaot-com/jason/issues/1114) and [Copier Service Manual #1115](https://github.com/al-teamaot-com/jason/issues/1115) for overlap before proposing any TODO. Being linked does **not** establish that every sub-idea was implemented or approved.
- **Finance & Revenue Assurance (IDEA-0021 through IDEA-0038):** Original [18-idea cluster](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5981613306). Cross-check existing [Governed Billing Operations #403](https://github.com/al-teamaot-com/jason/issues/403) and QuickBooks/procurement work; these proposals are **read-only discovery concepts**, never financial mutation authority. The procurement-to-payment monitor and Financial Integrity Monitor are related views of the same end-to-end assurance problem; **do not split into separate engines** without evidence.
- **Usability / onboarding (IDEA-0039):** [Owner idea](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-5983051128). This concerns *onboarding Jason as an AI technician*, not the distinct client-device onboarding process.
- **Optional orchestration research (IDEA-0040):** [Paperclip owner suggestion](https://github.com/al-teamaot-com/jason/issues/877#issuecomment-6046784948). Research-only; Jason, Autotask and existing policy/approval/tenant controls stay authoritative. Unrated until technical evidence; **no pilot or replacement has been authorized here**.
- **Other ideas already advanced to TODO issues:** [Vendor Automation Intelligence #938](https://github.com/al-teamaot-com/jason/issues/938) and [Jason Everywhere / Alexa #1475](https://github.com/al-teamaot-com/jason/issues/1475). These are **reference links, not newly re-created Ideas or approval changes**.
- **Discovery process:** [Ideas List #877](https://github.com/al-teamaot-com/jason/issues/877); **employee no-approval submission design:** [#1519](https://github.com/al-teamaot-com/jason/issues/1519). One list, not a second scheduler or TODO-intake worker.

## Adding an idea later

A human can simply say, **"Jason, idea: show technicians which client sites have repeated print failures."** The intended intake stores its original words and submitter, returns the new IDEA ID, and optionally suggests **Client Experience & Service · Medium potential**. That example is illustrative, **not an added item or a working submission endpoint**.

When another idea looks similar, link IDs; do not erase the earlier suggestion or its author. When a well-defined candidate is promoted, add the exact TODO link to all source IDEA records and preserve category/value as historical suggestion metadata. If the suggestion is a confirmed defect in currently approved behavior, send it to existing Support triage.

## Non-interruption and next gate

**Documentation-only staging:** This change does not edit the protected-main TODO or Support source, start a daily brainstormer, add/assign GitHub tasks, schedule a worker, alter customer/finance data, change approvals, run scripts, merge code or deploy. Existing Production Manager [#1078](https://github.com/al-teamaot-com/jason/issues/1078), TODO worker [#1196](https://github.com/al-teamaot-com/jason/issues/1196) and Universal Teams Approver [#1440](https://github.com/al-teamaot-com/jason/issues/1440) remain higher priority. Actual Ideas List app/submission/automation must be released and independently verified under [#877](https://github.com/al-teamaot-com/jason/issues/877) and [#1519](https://github.com/al-teamaot-com/jason/issues/1519) only when their gates allow it.
