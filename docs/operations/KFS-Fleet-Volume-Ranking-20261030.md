# KFS fleet month-to-date ranking: governed read-only acceptance

Owner: AOT Copier Operations · Issue #2176 · PR #2177 · 2026-10-30

## Expected experience
An authorized AOT staff member can ask "Jason, what are our top 5 highest-volume printers for October 2026?" Jason selects `print.fleet.usage.rank` through governed resource interpretation and returns customer, equipment ID, B&W pages, color pages, total impressions, latest reading timestamp, and coverage/exception details. No user-uploaded KFS spreadsheet, device ID, or direct provider credential access is required.

## Data contract
- Source of truth for inventory: the latest completed successful `kfs_runs` row at or before the reporting period end, and the corresponding `kfs_device_status_readings` rows. Check `device_count`, `error_count=0`, unique device IDs, and snapshot freshness (at most 36 hours).
- Meter source: read-only `kfs_meter_readings` sampled near the period-start and period-end boundaries, with a configurable bounded window (default 36 hours). All SQL parameters are bound; no side-effecting statements.
- For the current month, stop at the present observation time. Never extrapolate to month-end. A prior month uses the specified month boundaries in the requested timezone.
- Rankings are by nonnegative, actual `total` impression difference. Require matching B&W and color deltas and `B&W + color = total`. Scans are excluded. Stable tie-break by device ID.
- Report `complete=true` only if the successful inventory is fresh, its reported and enumerated device counts agree, no current devices are missing, and all included devices have usable B&W/color/total deltas. Otherwise identify the report as provisional and list exceptions; never present a partial ranking as authoritative.
- Data gaps may be legitimately caused by offline/nonreporting printers. Such gaps are not estimated or silently excluded.

## Scope and guardrails
- AOT organization observe-only; tenant/client scoped calls remain denied until approved mappings exist.
- No endpoint changes, service restarts, printer changes, ticket updates, new provider permissions or credential handling outside current governed KFS read path.
- The preproduction branch does not alter production until a separately authorized controlled release.
- No change to other pending PRs #2125/#2126/#2128; their overlapping `composition.py` portions should be reviewed during integration.

## Validation
- KFS connector, catalog, authority and history tests.
- A literal LaToshia query end-to-end metadata/plan routing test, plus top-ten and unrelated-toner intent tests.
- 435-device fixture, missing boundary/reset, stale inventory, mismatched fleet counts and report completeness tests.
- Provider-backed acceptance: compare the actual live KFS full-fleet inventory with stored run counts, verify latest collection and exact October deltas, and rerun the same October query as Adam and LaToshia. Verify the same top five and exceptions.
- All required CI, overlap/standards/documentation gates, controlled release scope, last-known-good SHA, exact candidate SHA and postdeploy health must pass before deployment.

## Production readiness
Implementation and synthetic tests alone do **not** establish live KFS readiness. Until provider-backed acceptance succeeds, mark the capability NOT VERIFIED for production.

## Latest non-disruptive collector evidence (2026-10-30)

Observed on the authorized Jason host via **read-only** inspection of collector result summaries (not a preproduction execution of this PR):

| Completed UTC collector run | Result | Managed devices | Errors | Meter-reading rows |
|---|---|---:|---:|---:|
| 2026-10-30 16:00:01 | ok | 435 | 0 | 7,330 |
| 2026-10-30 10:00:02 | ok | 435 | 0 | 7,330 |
| 2026-10-30 04:00:00 | ok | 435 | 0 | 7,330 |

The 16:00Z collector run ID is `11ad789b-73eb-4762-8fa7-44f8124a70b4`. A successful collector summary supports inventory freshness, **not** the accuracy of October per-device deltas, the ranking, live AOT user routing, or the full database join. Those remain provider-backed acceptance requirements.

### Exact source scope caution

At this inspection, the running production runtime and `/opt/jason/current` both identify `cb76e14f9f42ec4f914b10967db1d408c271c1aa`. Protected main is ahead of that running release by one separate engineering-standards commit (five files, including `AGENTS.md` and the JES registry). A future merged KFS release must disclose that separate commit in the complete release scope and verify the root-pinned last-known-good release; the running SHA alone is not sufficient to claim rollback readiness. No merge or production deployment is implied here.

## Provider-backed report acceptance evidence (2026-10-30, read-only)

Using the exact PR development code in an isolated source checkout, the existing `kfs_reader` role and PostgreSQL transaction read-only mode, the October month-to-date batch query reconciled **435 of 435** current inventory devices against the completed collector run `11ad789b-73eb-4762-8fa7-44f8124a70b4`.

First pass: 219 devices had complete total/B&W/color deltas; 216 were flagged. Investigation of the source data established that 213 of those devices have no separate color counter **and** independently observed total and B&W deltas are exactly equal. This justifies derived *zero* color impressions with explicit provenance; it is not a usage estimate. Three devices lack required total and B&W boundaries and remain exceptions.

After applying the no-estimate monochrome rule and re-running the live read-only calculation, 432 devices had usable actual monthly deltas and 3 remained meter exceptions. **Do not claim full-fleet ranking certainty** while any inventoried device lacks bounds.

A separate KFS upstream customer-assignment gap is confirmed: only 131 of the 435 devices in the latest inventory have a nonempty `kfs_devices.customer_name`. The KFS group metadata did not supply names for four of the five current highest-volume devices; all four also have empty customer IDs, and the root group is shared by multiple unrelated customers. **Do not infer customer from a shared group**. The report explicitly labels unmapped customers and publishes the missing-mapping count rather than inventing a customer.

This source+live-data validation is not a deployed Jason user conversation acceptance. Normal user tests previously failed on production before this branch was merged. Required next evidence: current-head CI and controlled preproduction end-to-end conversation response, then exact merged SHA / root-pinned rollback verification and a separately authorized deployment. No production change has been made in these checks.

## Governed conversational presentation contract

The report response carries `report_type=ranked_monthly_usage` and `schema_version=1.0`. Jason's existing provider-neutral read renderer now formats that declared report deterministically after checking orchestration success, exact intent capability, provider provenance, count reconciliation, B&W+color=total, descending rank order, period alignment, and bounded row count. It does **not** ask a model to guess values or to fill blank rows.

The actual read-only October data was projected through the same `OrchestrationResult` / `ConversationIntent` rendering path in an isolated checkout. The output contained five numerical ranked rows, clear `Provisional` status, 435 inventoried, 432 usable monthly deltas, 3 meter exceptions, mathematically verified zero-color annotations, and 304 missing customer assignments. Four top-five customer labels remain `Unknown (not mapped in KFS)`; this is authoritative source-data incompleteness, not a rendering failure. AOT must establish an approved canonical KFS device-to-customer mapping before those names can be supplied.

This is source-level integration and provider-backed read evidence, **not** a live authenticated Teams end-to-end test, release eligibility, owner exact-SHA authorization, or production acceptance. Fail-closed status remains required.

## Supplemental AOT source evidence for unmapped top-five customers (read-only)

KFS currently has no populated canonical `kfs_autotask_mapping` rows, and its device/group customer identity is blank for four ranked machines. An internal AOT SharePoint search on the **exact serial numbers**, not on generic group names, found the following candidate owner records (all inspected read-only):

| KFS serial number | Document-backed customer | AOT equipment ID in document | Supporting source |
|---|---|---|---|
| `RRG2301432` | St. Matthews Catholic School | 1207, 8003i Teacher Work Room | `ST MATTHEWS CATHOLIC SCHOOL Log (ID# 1202, 1203, 1206, 1207, 1212).xlsx`, modified 2026-10-20; 2025 Configuration List |
| `1G55504297` | Atlantic View Operator | 1398, MZ6001i | `eCopiers (Virginia Health Services)14 machines (3 year CPC log).xlsx` modified 2026-10-23; AOT Delivery Receipt Equipment 2026, 2025 |
| `1G55503749` | Marcella Operator LLC | 1403, MZ6001i | Same KFS CPC log and AOT delivery receipt |
| `1G55503694` | Water Reed Operator | 1405, MZ6001i | Same KFS CPC log plus `Machine list.docx` |

Source lookup links (AOT authentication required):
- [St. Matthews log](https://absolnet.sharepoint.com/sites/AOTAdminDocuments/_layouts/15/Doc.aspx?sourcedoc=%7BDC8D82A6-8064-4EC6-8970-9E716D82D495%7D&file=ST+MATTHEWS+CATHOLIC+SCHOOL++Log+%28ID%23+1202%2C+1203%2C+1206%2C+1207%2C+1212%29.xlsx&action=default&mobileredirect=true&web=1)
- [Virginia Health Services CPC log](https://graph.microsoft.com/v1.0/drives/b!-IVayFBqaUWID9Jhxl3yuySnt-Wb3GtArtgpYfH3EVNo8p5rPdImQ5Z7APH0M9tF/items/01NWNXUCVHM2NI67XF5RELUAVFHBOFGIGJ)
- [AOT delivery receipts](https://graph.microsoft.com/v1.0/drives/b!-IVayFBqaUWID9Jhxl3yuySnt-Wb3GtArtgpYfH3EVNo8p5rPdImQ5Z7APH0M9tF/items/01NWNXUCSS7U666XAYMVAY77T7TRXUBGAQ)
- [AOT machine list](https://absolnet.sharepoint.com/sites/AOTAdminDocuments/_layouts/15/Doc.aspx?sourcedoc=%7B5A4D7211-E5A3-4D48-A131-9E6B0C985BAB%7D&file=Machine+list.docx&action=default&mobileredirect=true&web=1)

These are **candidate mappings supported by internal documents, not yet activated for Jason**, and they may represent different legal customer, site, equipment owner, and invoice/billing identities. To satisfy full reporting rather than hardcode the current top five, engineering needs an approved canonical device-serial to client identity source, conflict resolution precedence, owner audit and refresh policy, and a read-only governed mapping adapter. Neither empty `kfs_autotask_mapping` nor non-specific shared group ID `CNWZDCC` can act as affirmative customer evidence. Do not persist the four names into KFS, Autotask or production database without mapping authority and acceptance. Continue provider-backed usage report with conspicuous `Unknown (not mapped)` caveats in the meantime.


## Authorized supplemental SharePoint customer evidence (owner approval 2026-10-30)

The owner approved AOT's existing copier logs and delivery receipts **as supplemental read-only customer-identification evidence**. The approval is recorded in GitHub issues [#2176](https://github.com/al-teamaot-com/jason/issues/2176) and [#1117](https://github.com/al-teamaot-com/jason/issues/1117). It does **not** grant new Entra/Graph permissions, authorize credential reuse, allow provider writes, change KFS/Autotask records, or grant a production deployment.

Implemented on the current KFS development branch:

- \`kfs_customer_document_evidence.py\` accepts only versioned, bounded, pre-authorized AOT SharePoint \`.xlsx\` document bytes from an injected **trusted** governed source. It does not make Graph calls or access ChatGPT connector credentials.
- Parsing is non-destructive (\`openpyxl\`, data-only, read-only, external links disabled), with bounds on compressed/uncompressed size, sheet count, aggregate rows, individual row columns, and number of documents.
- Matches use exact serial numbers, a single explicit sheet-wide company label or a customer-specific named meter log corroborated by an in-sheet heading. Multi-customer row tables or stacked receipts without row-level association are intentionally NOT interpreted.
- Indexing requires an explicit approved Microsoft tenant, site, document library, source item identity, eTag and modification time. Stale documents and unsupported classes are rejected/excluded. An index may not silently add a source from another site or library.
- Multiple documents identifying one serial are corroboration only when their customer names normalize identically. Distinct names, including truncated/changed legal entity names, are **conflicts**. Different KFS and SharePoint customer names are also conflicts; the report marks the device for review instead of silently overwriting KFS.
- The KFS fleet report can consume an optional, immutable customer evidence index at its existing read-only calculation boundary. Mapping evidence in the output includes source drive/item, eTag, SHA-256 of source bytes, and worksheet. The file contents and credentials are not published in the report.
- With no authenticated document evidence supplied, behavior remains unchanged and missing customer names remain marked Unknown. This is the **default**. No new production runtime activation has occurred.

### Required authentication and information-release integration

Do not implement an ad-hoc SharePoint client in KFS. The reusable Microsoft Graph SharePoint reader already exists under [PR #1330](https://github.com/al-teamaot-com/jason/pull/1330) / issue [#1117](https://github.com/al-teamaot-com/jason/issues/1117), but is draft, not active in Jason production. It requires the dedicated Jason workload identity, verified AOT tenant/site/library selectors, document-level release policy, approved \`knowledge.document.metadata.read\` and \`knowledge.document.content.read\` capabilities, and a source-revision-consistent read before providing the approved document bytes to the index. **ChatGPT's separately connected delegated SharePoint account is not that identity.**

The KFS application must never read arbitrary site URLs, accept user-specified source paths or credentials, infer customer identity from shared KFS groups, or accept an unverified cached snapshot. It should fail closed if the approved reader cannot supply bounded current evidence or there are conflicting source records. A verified source materialization/refresh and evidence audit are dependencies before live Jason/Teams acceptance.

### Nonproduction evidence

An isolated development checkout passed a focused 31-test parser+fleet-ranking suite including explicit label extraction, same-sheet boundaries, two-source conflicts, source scope rejection, old source exclusion, a 435-device ranking fixture, and a corroborated single-customer log layout. Source eCopier workbook structure was examined through AOT's delegated SharePoint connector: separate worksheets have \`Company:\` and \`Serial #:\` labels, with serials \`1G55503749\`, \`1G55504297\`, \`1G55503694\`. One worksheet spells its customer \`Atlantic View Operato\`, whereas the AOT delivery receipt shows \`Atlantic View Operator\`; these are not automatically canonicalized without an approved alias decision.

These passing tests **do not** prove that Jason can authenticate to AOT SharePoint, ingest source documents unattended, or deliver a fully verified top-five report today. The latest GitHub CI must be checked against its exact head before release. Preserve the production freeze and separate exact-SHA approval.


### Version-consistent SharePoint connector adaptation

The approved evidence module now also accepts the **existing draft PR #1330** governed connector results, not raw arbitrary URLs. The adapter takes three separately authorized reads for the same exact document selector:

1. \`knowledge.document.metadata.read\` — site, drive, item, size, MIME type, last-modified time, and version/eTag.
2. \`knowledge.document.content.read\` — bounded base64 document bytes and source SHA-256 from the approved reader.
3. \`knowledge.document.metadata.read\` again — same exact source identity and unchanged eTag/version to detect a source change across the read.

It verifies source provider and operation, selector identity, MIME type, size, SHA-256 digest, and consistent before/after version before creating an approved workbook object. Tests cover wrong provider, wrong operation, source ID mismatch, content SHA mismatch, MIME mismatch, version changes, and the positive reader-to-serial-index path. It does not authorize any read by itself.

**Identity boundary still requires integration:** PR #1330's current \`GovernedSharePointConnector._tenant\` requires a non-empty \`ConnectorContext.client_id\` matching the validated Microsoft tenant binding. KFS \`print.fleet.usage.rank\` is an AOT organization-only report with \`client_id=None\`. An approved AOT-owned organization-scoped document-service identity/binding and document-release policy must be designed, tested and authorized within #1117 without loosening client isolation for other tenants. The code **must not** fake a client ID, borrow an end-user ChatGPT delegated token or bypass the connector to obtain document bytes. This requirement is not yet implemented or production-verified.

**What is implemented and tested now:** optional, disabled-by-default parser/index and report enrichment, plus the verified output-shape adapter. **What is not:** unattended Jason authenticated SharePoint collection, automatic refresh, full AOT document mapping, the three KFS meter exceptions, authenticated user acceptance, or production deployment.

## October 30 integration-gate review: PR #2178

## October 30 integration-gate review: PR #2178

The required repository-hygiene job identified PR #2178 as an overlapping active change to `implementation/runtime_service/src/jason_runtime/composition.py`. Its three added blocks register **Datto RMM patch-policy and site-patch read operations** at the endpoint imports, invocation mapping, and invoker registry. This KFS PR modifies separate print capability imports and mappings, a KFS meter-history invoker, and reporting metadata. The inspected hunks do not replace any #2178 functionality, and neither PR was merged. **Integration coordination: #2178** is declared in this PR body. Preserve both patch-read registrations during later protected-main reconciliation, and retest all concerned provider-read paths. This update repairs documentation of an identified overlap; it does not bypass the repository gate or attest live production acceptance.

## October 30 — Runtime integration staged, default OFF

## October 30 — Runtime integration staged, default OFF

The normal KFS runtime composition now includes a **disabled-by-default** governed SharePoint copier-document evidence path; no direct provider bypass and no normal user-selectable document URL.

- \`JASON_KFS_COPIER_EVIDENCE_ENABLED=false\` is the default. It requires \`JASON_KFS_ENABLED=true\` and an approved root-managed \`JASON_KFS_COPIER_EVIDENCE_MANIFEST\` if explicitly enabled.
- The exact AOT source selectors and reference are in \`config/preproduction/aot-kfs-copier-documents.example.json\`, which deliberately contains a non-date approval-expiration placeholder and **cannot be activated as committed**. Only an approved, fresh expiring (≤30-day) manifest installed to a trusted path can be used; symlinks, writable/unowned manifests, unbounded documents and wrong tenant/organization/service identities are rejected.
- The dedicated SharePoint OpenBao role/secret files must exist at the configured separate paths; missing files fail startup before Graph initialization. No fallback to existing directory/mail credentials.
- When enabled, the runtime composes the standard \`GovernedSharePointConnector\` from PR #1330 with AOT-only service identity binding and exact, expiring per-document grants, then creates a \`GovernedAotCopierSourceLoader\` and bounded 24-hour claim cache.
- Only a normal authorized AOT \`print.fleet.usage.rank\` operation invokes that cache, after the existing organization/permission gate. It reads the exact approved documents via metadata→content→metadata, verifies same-version SHA-256 and size, then passes an immutable customer-evidence index to a copy of the read-only KFS history store. A failed/expired document refresh does not reuse stale customer evidence.
- No SharePoint documents, secrets, or bearer tokens are written to KFS meter tables, Autotask, or public logs. Default-off KFS remains usable, but missing names are still flagged.
- The isolated KFS development branch tests validate strict manifest parsing, nonactivation of the placeholder, unsafe selector rejection, missing dedicated credential gating, disabled composition path, unauthorized request handling, and snapshot expiry. In a temporary combined KFS + SharePoint checkout, the enabled constructor path and governed connector compatibility have passed. **No production feature activation or live Graph read occurred**.

Source selection has been verified by the AOT delegated SharePoint connector: AOT Admin Documents site ID \`absolnet.sharepoint.com,c85a85f8-6a50-4569-880f-d261c65df2bb,e5b7a724-dc9b-406b-aed8-2961f1f71153\` and its Documents drive; three reviewed source IDs are in the inactive manifest. This discovery does not establish Jason workload access.

**Outstanding external actions:** dedicate/provision the SharePoint read AppRole, validate the AOT \`microsoft_graph_sharepoint\` tenant/client boundary and release grants, test authorized and forbidden Graph calls with service identity, then complete authentic user-question acceptance, scope, rollback and owner exact-SHA deployment approval. The three offline/unreadable monthly KFS printer meters remain explicitly flagged, not estimated.

## October 30 final preproduction security and provider evidence

## October 30 final preproduction security and provider evidence

**Exact source scope:** This is a controlled internal AOT observe-only report. The approved documents are three exact items under AOT Admin Documents, not all of SharePoint. The three source IDs and the AOT tenant ID are already in the inactive preproduction manifest.

**Consent and credential facts verified read-only on the running Jason host:**
- The live Kernel client-boundary database contains one validated AOT directory-read profile and separate AOT mail profiles, all for tenant \`f7054323-d52b-4863-8c2f-1898f0b6077c\`, client \`client-aot-internal\`.
- **No** \`microsoft_graph_sharepoint\` / \`sharepoint-read\` validated binding is registered. This is an independently verified authorization blocker.
- The canonical command \`python3 tools/provider_secret.py create microsoft_graph_sharepoint --check-only\` returned \`status=pass\` and \`network_contacted=false\`; it validates the secret lifecycle **contract only**.
- The current nonprivileged remote command identity cannot stat the root-protected SharePoint AppRole directory; \`sudo -n\` requires a password. Therefore credential **presence or absence is not independently verified**. Earlier statements describing the AppRole as definitely missing should not be relied upon without a privileged metadata check.
- The SharePoint reader development documentation identifies an Entra application and registered public certificate; actual application consent and private key availability require a privileged read-only confirmation. Do not import/reuse an existing mail or directory AppRole in its place.

**New release guards:** The SharePoint runtime now demands a separate consented \`microsoft_graph_sharepoint\`, \`sharepoint-read\`, \`client-aot-internal\`, \`teamaot.com\` boundary with validated state and service principal. AOT document evidence is invalidated on **every** use if the root-managed exact-source manifest changes, the boundary is revoked, or its approved expiration has passed, even if cached data is under 24 hours old. These checks are strictly in the preproduction branches and do not alter the running production runtime.

**October full-month exceptions:** Three inventoried KFS devices have no verifiable October start boundary: \`1FU6517861\` first reported October 20, \`RC10103305\` first reported October 12, and \`RC11Y06141\` has no meter-history rows. Do **not** infer their October 1 counts or report fleet-wide complete usage. Current month-to-date ranking from the other 432 valid records remains explicitly provisional.

**Validation:** Both development branches merge without conflicts in an isolated checkout. The latest combined read-only source integration, protected identity, exact-document authorization, and KFS regression suite passed 142 tests with engineering standards PASS. The newest GitHub overall Jason CI jobs on each PR were blocked by installation **API rate limit HTTP 403** in \`tools/change_integration_gate.py\`; they did not show functional assertions failing. The gate remains required, and the PRs remain unmerged drafts. No provider credential was accessed or production modification performed in this investigation.

### Remaining operator-facing dependencies (not implicitly approved)

1. Have an appropriately privileged owner verify the existing **dedicated** registered SharePoint Entra application, consented read scope, and root-staged certificate metadata without disclosing private keys. Provision the canonical isolated OpenBao AppRole/credential profile only through the approved controlled release procedure.
2. Create/validate the exact AOT \`microsoft_graph_sharepoint\`, \`sharepoint-read\` Kernel boundary using the canonical identity process and actual Entra application/service principal. Do not manually forge a validated record.
3. Install a root-managed, time-bounded allowlist manifest from the preproduction template. Authorize only the three reviewed document IDs and keep document content internal.
4. Run positive and negative **provider-backed** Graph tests using Jason's dedicated identity, including mismatched tenant, wrong document and revoked grant, then perform an authenticated Adam/LaToshia report query.
5. Resolve or clearly preserve the three meter gaps, review customer-name differences such as \`Marcella Operator\` versus \`Marcella Operator LLC\`, clear all required GitHub/release gates, verify exact merged release and rollback SHA, and obtain final owner exact-SHA deployment authorization.

Production KFS/SharePoint functionality has **not** been deployed or verified.
