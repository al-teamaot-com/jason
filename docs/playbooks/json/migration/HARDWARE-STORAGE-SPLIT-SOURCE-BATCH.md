# JSON conversion batch — Disk Event 7, POST, Low Disk, VulScan split

## Section Goal
Convert four legacy structural partial drafts to independently testable,
source-specific PMv4 JSON candidates using the existing interpreter,
existing source classifiers and governed action-port declarations.
Every conversion is **source-only and not accepted**. No live provider
write, production Core/Stage E mutation, JSON activation or legacy retirement.

## Source-bound candidates

**Windows Low Disk Space**
- Source: `docs/playbooks/Jason-Windows-Low-Disk-Space.md`.
- JSON: `candidates/low_disk_space.v1.json`, version
  `1.1.0-migration.2`, fingerprint
  `8ddfe6f27137480d72b22e750ad9b1b8953e1cd73309b73a46ab12b632622959`.
- `json_low_disk_classification.py` reuses existing
  `storage_health_summary`, `choose_cleanup`,
  `relevant_findings`, `artifact_bytes` and `recommendation`.
  It checks current volume and client/device identity, 15-minute
  Autotask grace, storage risk, safe workstation versus protected server,
  and currently open monitor before planning one exact Sysmon cleanup.
  SoftwareDistribution cleanup is deliberately review-bound. No actual
  file deletion/job is executed.
- Tests: `test_json_low_disk_classification.py` verifies same-source
  cleanup decision, storage health, servers, stale/missing evidence,
  user/system data, no competing cleanup and interpreter approval denial.
- Missing: complete read-only large-file/VSS/disk evidence fanout,
  approved exact component, job output and provider monitor/readback,
  durable recheck and governed live preproduction acceptance.

**Windows Event ID 7 / bad-block**
- Source: `docs/playbooks/Jason-Windows-Disk-Bad-Block-Event-ID-7.md`.
- JSON: `candidates/disk_bad_block_event_7.v1.json`,
  `1.0.0-migration.2`, fingerprint
  `6bde35361a6732af1dd75e6ffe4ceef86f8a96ca91079a577a1edebb414ac427`.
- Source adapter `json_hardware_triage.py` reflects the **currently
  deployed conservative diagnostic**: exact alert/endpoint identity,
  storage Event ID 7, disk number and removable USB hints. It does NOT
  infer physical removable versus internal storage from a disk number
  and does NOT resolve DRMM alert. Exact note and Help Desk I handoff
  are separately approval bound.
- The broader authored removable-media auto-resolution requires
  physical-disk mapping and **ungranted** `endpoint.alert.resolve`
  authority. Original registry allows note and ticket state only.
- Missing: controlled disk diagnostic, physical serial/bus mapping,
  approved alert-resolve source amendment, exact note/status readback
  and preproduction acceptance.

**Windows POST Error Investigation**
- Source: `docs/playbooks/Jason-Windows-POST-Error-Investigation.md`.
- JSON: `candidates/post_error_investigation.v1.json`,
  `1.0.0-migration.2`, fingerprint
  `6d93920c32e13583c40a74fee13d31d72dc7d2c7f3744a645836d390a0b2f9cc`.
- Reuses `json_hardware_triage.py`, reflecting deployed POST
  diagnostic: exact device, alert history, recurring/protected role,
  and conservative Human Review handoff. No speculative hardware
  changes or autonomous alert resolution.
- Missing: full WHEA, BIOS, boot and hardware evidence, approved exact
  alert-resolution authority for isolated healthy workstation branch,
  ticket/note provider readback, source parity and preproduction acceptance.

**VulScan Multi-Device Split**
- Source: `docs/playbooks/Jason-VulScan-Multi-Device-Split.md`.
- JSON: `candidates/vulscan_multi_device_split.v1.json`,
  `1.0.0-migration.2`, fingerprint
  `c3b693dd1d5ee17309a8281ef21d3cee5ccad4893e5c0f9f6fa7062a3c6ab318`.
- `json_vulscan_split_plan.py` reuses deployed VulScan affected-node
  parser and the **existing `TicketSplitRequest` and
  `TicketSplitTarget`**, exact active same-company CI, DRMM UID/
  hostname and source lineage marker. Duplicate sources, duplicate UID,
  ambiguous CI, partial pages and cross-company endpoints fail closed.
- Tests `test_json_vulscan_split_plan.py` compare exact source ticket,
  two unique device children and deterministic marker with the existing
  split primitive, and deny unsafe duplicate/company/identity branches.
- Missing: native JSON runtime's durable per-target iteration through
  existing `SQLiteTicketSplitStore` and `TicketSplitExecutor`,
  exact full governed parent claim -> verified children -> lineage note
  -> source completion, no replay after ambiguous provider write, and
  real isolated provider-connected acceptance.

## Independent acceptance and remaining gates
All four source-specific synthetic tests and corresponding interpreter
approval denials passed locally. Unchanged legacy runtime and other
PMv4 components are not modified. Source JSON never grants permission
or execution authority.

**Full authored parity: NOT VERIFIED for these 4.**
**Live provider-connected preproduction acceptance: NOT VERIFIED.**
**Production activation/legacy retirement: NO.**
