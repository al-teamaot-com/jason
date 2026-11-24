# P0 — one bounded Owner decision to complete interrupted daily audit-journal migration

**Engineering source / production status:** This document and companion source do **not** authorize or execute a production release. The currently effective freeze, release-control, single-use execution, typed exact Owner and native drift gates remain enforced until a new, independently verified and reviewed objective grant is created.

## Problem and verified Root/host evidence

The 2026-11-23 original 47 GB audit SQLite migration stalled after the owner-approved release's Root helper lacked the effective CAP_SETUID. A fresh 2026-11-24 exact recovery installed the already reviewed ambient CAP_SETUID service-line correction and queued a new Owner scope, but Docker 29 normalized `HostConfig.OomKillDisable:null` to the effective `false`, causing `AUDIT_RELEASE_UNKNOWN_REPLACEMENT_CONFIGURATION`. The automated rollback hit the same comparison. Two follow-up exactly Owner-authenticated recoveries independently restored ticket-core and removed the two legacy admission triggers. All prior Root approvals and both stopped rollback containers remain preserved.

Current verified legacy state (2026-11-24 ~08:43 EST):
- Canonical SQLite original dev **66306**, inode **10261846**, ~47.4 GB, 34.5M+ event rows, owned UID/GID1000, mode0600, and zero `audit_journal_maintenance_%` triggers.
- Ticket-core ID `795c5c2876bb676e797813383d50dd540d5a52b44e04ebb31b95e576ea72f1e5` **Running + Healthy**; `jason-runtime` Running + Healthy, `jason-mcp-pilot` Running; both stopped original/failed ticket-core rollback containers retained.
- Installed 3 systemd service units contain reviewed `AmbientCapabilities=CAP_SETUID` and match protected Main byte-for-byte, no broader service unit edits.
- Installed 12 trusted journal source modules match protected Main **except `tools/audit_journal_container_release.py`**, whose reviewed one-direction Docker 29 default-normalization fix is already merged in protected Main. No SQL, journal, archive, health or native Root code source delta.
- Existing Root journal release **failed and quiesced**, maintenance timer disabled, protected native drift breaker **OPEN**, production freeze unchanged. Original Root record `ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3` has only the incomplete ticket-core `install` and `restore` steps. The old eight-hour claim cannot be replayed.
- Separate archive drive `/srv/jason/archive` now has **174,159,179,776 free bytes** after lossless compression of one unused offline staging prototype; the raw original 26.2 GB prototype was deleted only after exact decompressed SHA, source custody, independent backup and no open holders passed. 22.52 GB reclaimed, archive reserve >27 GB above installer requirement. The historical 6.2GB safety snapshot and compressed offline prototype remain; no live database or archive journal changed.
- Live universal approval ledger has one existing `plan_grants` record, **not audit-journal**; Root audit installer still uses legacy `auth["owner"](scope)` per action, while production `JASON_UNIVERSAL_APPROVAL_MODE=off`. These facts do not justify fabricating a reusable approved grant from consumed exact-action records.

## One reviewed bounded plan

New action: `COMPLETE-REMAINING-BOUNDED-DAILY-AUDIT-JOURNAL-OBJECTIVE`.

The Owner reviews one complete Root-owned plan: protected source Main commit, rollback `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`, live host, exact files/containers, known interruption, source repair, archive/Root storage effects, time budget, all six allowed stages, five bounded recovery branches, preserved immutable failed records, runtime availability, native freeze, and observable end-to-end acceptance. An independently authenticated **licensed AOT Owner Entra decision** mints one Root0400 grant with its exact scope and a new, separate one-use release claim; earlier exact-action grants are evidence only, never replayable authority. Production is never authorized solely by this documentation, GitHub merge, Owner chat assertion or code tests.

### Included reviewed stages

1. Reconcile old interrupted legacy release without overwriting its original plan, journal or approval evidence.
2. Refresh only the reviewed Docker 29 matcher (a single benign `OomKillDisable:None -> False` comparison), new source hashes, immutable current original producer identities and source profile. Preserve all other trusted source and unit bytes.
3. Queue **one new** full journal migration under a fresh eight-hour executed claim and existing approved rollback, after Root source/custody, completed protected Main CI, current Owner, exact native incident, archive spare space and mounted DB identity checks.
4. Seal all historical journal segments, verify event parity and independently reconstruct/cold-restore original data using the installed reviewed release executor (not ad hoc table copying).
5. Prove genuine new writes across the small active journal and historical archives, actual scheduled daily rollover, Root native full+fast health and independent drift PASS.
6. Reclaim redundant original Root storage only after all source and recovered lineage checks PASS, preserving sealed archive and backup evidence.

### Included bounded recovery branches

- Reconcile an ambiguous Docker transport outcome by exact native readback once; never blindly replay provider mutation.
- If the new release fails **before cutover**, recover/restore the original producer configurations and exact known barriers under its original reviewed rollback branch.
- Retain all original/failed before-images, sealed journal, Root receipt and required restore assets on failure; no ad hoc cleanup.
- Roll back only within the newly approved eight-hour claim and established native safety/rollback gates. A partially **queued** service must not be restarted by the pre-queue recovery helper.

- Roll back a not-yet-queued Root installation and resume the same exact transaction **once** under the still-valid Owner plan; reject a revoked, stale or ambiguous queued claim.

### Pre-queue continuation without duplicate Owner approval

`--resume-bounded-audit-objective` is available **only** if a newly issued Root objective grant already exists for the exact approved commit and action, remains within its eight-hour validity, and the original release **was not queued**. It refuses a changed plan fingerprint, revoked/expired scope, consumed retry, unknown Root file or mode, unexpected protected state, current running/mutated service, or any foreign transaction entry. Under the original Root host mutation lock, it durably records **one** prequeue resume attempt, reconciles the recorded before-images transactionally and independently revalidates the original complete source/Root/native/peer/Owner plan. The same Owner decision and recorded original timestamp are reused, with no second Entra challenge. No queued/unknown state replay is permitted; a materially new or wider action still requires an amended complete plan.

This is **not** standing unlimited Root authority and does not activate the general universal approval system for all AOT users. A separate reviewed activation of that production-disabled service is tracked in #1440. This implementation fixes the journal-specific objective boundary using the existing signed licensed-Owner exact verification and Root audit ledger; it does not forge an old global approval record.

## Safety and QA

- The Root-only preflight independently requires the original candidate+scope, exact prior verified Entra Owner receipts and successful ticket-core/admission restoration, historical Root files and one exact failed journal state. It rejects change or deletion of any protected history.
- Native drift must be exactly known failed journal/timer/watchdog. The protected breaker remains **OPEN** until independent native evaluator closes it legitimately. Unexpected unrelated drift, stale observation, unapproved container IDs/images/configurations, foreign DB readers, extra archive files, a changed schema, bad source hash, missing mount, low disk reserve or replay all fail closed.
- The protected 11 unchanged source modules and all systemd unit bytes are independently SHA-matched. The new Root release modifies only eight exact files: trusted Docker matcher (Root0444), two Root0444 profile files, Root0600 policy, four Root0400 current producer/adoption/plan/journal records. Their old images are kept in a Root-only transaction and never overwritten without exact source verification.
- The existing Root-only installed worker performs the only permitted cutover/rollback; this new helper does **not** directly write SQLite tables, restart Docker daemon, reset the network, clear the breaker or alter unrelated services. It records a durable one-use transaction **before** enabling/starting systemd.
- Focused tests: both verified previous rescue claims, mismatched previous scope/Owner, changed Docker source/hardening, unexpected drift and aged breaker, healthy restored producer proof, fresh plan/producer IDs and journal claim construction, one original Owner denial, prequeue continuation without owner callback, expired/wrong/revoked/replayed grants, unknown Root mutation target, dangerous mode, duplicate entries. Full audit-journal test suite and all required protected GitHub security/CI checks must pass on the final merge SHA before any production execution.

## Activation and 100% acceptance gate

No source merge or Root `QUEUED` result constitutes completion. The Root release must actually report `accepted` and independent checks must confirm active segment mode, all original event IDs/counts, new appended events, cold restore/reconstruction, sealed history and retention, enabled and observed maintenance timer, actual full+fast health and independent native drift PASS, legitimately closed breaker, no lost protected peer, expected exact current container images/configurations, correct off-host/archive custody, and demonstrably reclaimed original 47GB Root disk allocation. Any failed condition is **incomplete** and requires the included, exact governed recovery branch rather than generic commands or repeated blanket approval prompts.

**User boundary:** This chat's unprivileged Remote Desktop Commander cannot invoke Root or synthesize Entra Owner identity. When protected Main CI, source, Root preflight and full plan are ready, present at most **one exact Root invocation with one authenticated full-plan approval**. Do not present multiple diagnostic sudo instructions. Future material-out-of-scope approval is a new decision boundary, not a reason to replay past approvals.

Tracking: #2680, #1440; past engineering #2714–#2718. No production activation performed by this document.


## Rollback-container capacity verified before Owner interaction

The live pre-repair Docker inventory has **20 exited role-specific rollback containers** and one additional Created dormant planned audit rollback container. The reviewed original release requires a maximum of **21 pre-release exited backup containers** and six additional slots (three planned and three exact recovery roles). The bounded Root preflight now independently runs the exact stopped-container Docker inventory, checks names/uniqueness, matches original scope's reserved-slot contract, and denies if current role-specific exited rollback count exceeds 21 or cannot reserve all six required new slots. Its count, names and dynamic reserve are recorded in the authenticated objective scope and rechecked immediately after Owner authorization. The Created dormant planned container is preserved, not used as spare space or deleted. Neither this capacity proof nor the Owner plan permits deleting old stopped backup containers.
