# Jason P0 incident reconciliation and shared root-cause analysis — read-only baseline

**Recorded:** October 17, 2026. **Source:** [main/SUPPORT.md](https://github.com/al-teamaot-com/jason/blob/main/SUPPORT.md) at blob `395a6d2a4afeb934c99b3cb810bc829af2bf2ad7`, with selected linked GitHub issue-state reads made on the same date.  
**Status:** Documentation-only audit staged outside main; **not live incident health, confirmed root cause, repair authorization, or a request to reprioritize work.**  
**Existing ownership:** [self-heal / SUPPORT-OPS-029 #635](https://github.com/al-teamaot-com/jason/issues/635), [TODO / engineering reconciliation #1196](https://github.com/al-teamaot-com/jason/issues/1196), [Production Manager #1078](https://github.com/al-teamaot-com/jason/issues/1078), [Resolution Memory / TODO-OPS-001 #951](https://github.com/al-teamaot-com/jason/issues/951), [ticket worker #770](https://github.com/al-teamaot-com/jason/issues/770) and [cross-workflow shared-service adoption #1535](https://github.com/al-teamaot-com/jason/issues/1535). **Do not create competing incident, priority, retry, release, ticket, or autonomous engineering control planes.**

## A. Findings: what is knowable now

| Observation | Verified from current records | Why it matters |
| --- | --- | --- |
| P0 Support List rows | **23** (5 marked Open, 18 marked In progress) | Recorded status != present-day confirmed broken behavior |
| Unique P0 support identifiers | **22** | ID alone cannot safely distinguish all incidents |
| ID collision | **`SUPPORT-OPS-046` has two unrelated records**: Microsoft Graph health canary and self-heal correlated symptoms | Never merge or deduplicate those records by ID alone; use an exact stable incident identity and preserve both original entries |
| Preliminary group candidates | Release/host integrity **15**, engineering/admission **6**, provider health **1**, self-heal/root cause **1** | Groups are **review queues / possible shared failure domains**, not proven common root causes or a reduced unique P0 count |
| Closed linked GitHub tickets whose corresponding Support List rows still say Open | [#1317 / SUPPORT-OPS-057](https://github.com/al-teamaot-com/jason/issues/1317), [#1313 / SUPPORT-OPS-056](https://github.com/al-teamaot-com/jason/issues/1313) | **Reconciliation candidates only**: GitHub closure is not sufficient to assert that original symptoms are production-verified, or to close the Support row |
| Open linked GitHub issues for other explicitly linked P0 records | [#1493](https://github.com/al-teamaot-com/jason/issues/1493), [#1304](https://github.com/al-teamaot-com/jason/issues/1304), [#1301](https://github.com/al-teamaot-com/jason/issues/1301) | Account for both P0 engineering/support blockers and operational root-cause work |
| Operational severity / closure evidence | **Not established** from GitHub text alone | Live authoritative detector readback, protected host evidence and per-workflow status remain required |

**Important:** GitHub search for open issues with `P0` in their titles returned 15 in the earlier same-day check, but issue-title search is not an authoritative count of actual P0 incidents; the sets overlap and should not be added together. The source `SUPPORT.md` contains more metadata than shown here. This snapshot does not change any of it.

## B. Current P0 record inventory — grouping is provisional, no claims of shared cause

| Row | Support ID | Historical recorded state | Candidate failure domain | Explicit issue link |
| ---: | --- | --- | --- | --- |
| 1 | `SUPPORT-DEV-1440` — Teams approval engineering reasoning transport fails before owner-approved issue #1440 can enter implementation | Open - issue #1493, 2026-10-16 | Engineering / Support intake | [#1493](https://github.com/al-teamaot-com/jason/issues/1493) (open) |
| 2 | `SUPPORT-OPS-057` — Release Manager scheduled promotion proceeds while CCC certification is `NOT_PROVEN` for runtime-sensitive source changes | Open — verified 2026-10-12; issue #1317 | Release integrity / host drift | [#1317](https://github.com/al-teamaot-com/jason/issues/1317) (closed) |
| 3 | `SUPPORT-OPS-056` — Release Manager can falsely close then rollback a healthy production release due incompatible release-record schema | Open — verified 2026-10-12; issue #1313 | Release integrity / host drift | [#1313](https://github.com/al-teamaot-com/jason/issues/1313) (closed) |
| 4 | `SUPPORT-OPS-054` — GitHub P0 support issues can be silently excluded from autonomous engineering admission | Open — verified 2026-10-12; issue #1304 | Engineering / Support intake | [#1304](https://github.com/al-teamaot-com/jason/issues/1304) (open) |
| 5 | `SUPPORT-OPS-053` — Jason CCC and production drift watchdog scheduled units failing | Open — verified 2026-10-12; issue #1301 | Release integrity / host drift | [#1301](https://github.com/al-teamaot-com/jason/issues/1301) (open) |
| 6 | `SUPPORT-OPS-052` — Production control-plane drift includes stale queued release and developer-path user units | In progress — auto-detected 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 7 | `SUPPORT-OPS-051` — Toner exporter restart-loops on removed developer checkout path | In progress — auto-detected 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 8 | `SUPPORT-OPS-050` — Release Control Board reports healthy from stale production-health evidence | In progress — owner-reported 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 9 | `SUPPORT-OPS-049` — Release Manager policy declares serialized promotion but permits concurrent production transactions | In progress — owner-reported 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 10 | `SUPPORT-OPS-048` — Root host reconciler validates the candidate but executes the currently installed reconciliation script | In progress — auto-detected 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 11 | `SUPPORT-OPS-047` — Privileged host reconciliation still dereferences the mutable developer checkout | In progress — auto-detected 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 12 | `SUPPORT-OPS-046` — Microsoft Graph provider health canary falsely escalates as a login/authorization failure | In progress — owner-reported 2026-10-07 | Provider health / scope | Not explicitly linked in row |
| 13 | `SUPPORT-OPS-046` — Self-heal can treat correlated symptoms as separate incidents, repeat point repairs, and escalate owner action after bounded attempts without proving a real authority/disruptive blocker | In progress — owner-approved 2026-10-07 | Self-heal / common root cause | Not explicitly linked in row |
| 14 | `SUPPORT-OPS-045` — Production can close while scheduled user-level workers/watchdog remain on an older release | In progress — owner-reported 2026-10-07 | Release integrity / host drift | Not explicitly linked in row |
| 15 | `SUPPORT-OPS-044` — Owner-approved work can strand before Release Manager while status reports idle/nothing pending | In progress — owner-reported 2026-10-06 | Engineering / Support intake | Not explicitly linked in row |
| 16 | `SUPPORT-OPS-043` — Release Manager pre-production state clone recursively copies its own destination and can exhaust host disk | In progress — auto-detected 2026-10-04 | Release integrity / host drift | Not explicitly linked in row |
| 17 | `SUPPORT-OPS-042` — Release Manager falsely reports protected checks missing when merge SHA has more than 30 check runs | In progress — auto-detected 2026-10-04 | Release integrity / host drift | Not explicitly linked in row |
| 18 | `SUPPORT-OPS-041` — Release Manager can close a production release while runtime, MCP, and immutable host release are revision-divergent | In progress — auto-detected 2026-10-04 | Release integrity / host drift | Not explicitly linked in row |
| 19 | `SUPPORT-OPS-040` — Blocked Support items can starve governed TODO engineering forever | In progress — auto-detected 2026-10-03 | Engineering / Support intake | Not explicitly linked in row |
| 20 | `SUPPORT-OPS-039` — Engineering/TODO scheduled worker is bound to mutable developer checkout | In progress — auto-detected 2026-10-02 | Engineering / Support intake | Not explicitly linked in row |
| 21 | `SUPPORT-OPS-038` — Engineering/TODO host-worker installer cannot activate systemd user timer from non-login execution context | In progress — auto-detected 2026-10-02 | Engineering / Support intake | Not explicitly linked in row |
| 22 | `SUPPORT-OPS-037` — Release Manager post-cutover verifier treats normal health `starting` as immediate failure | In progress — auto-detected 2026-10-02 | Release integrity / host drift | Not explicitly linked in row |
| 23 | `SUPPORT-OPS-036` — Release Manager host activation/deployment-source binding failed first production acceptance | In progress — auto-detected 2026-10-02; PRs #818/#819/#820 | Release integrity / host drift | Not explicitly linked in row |

### Potential root-cause relationships to **investigate**, not assume

- **Release integrity / drift:** compare `SUPPORT-OPS-041/045/047/048/049/050/052/053/056/057` and the active [#1078](https://github.com/al-teamaot-com/jason/issues/1078) version/manifest/CCC requirements. An old unit, incompatible controller schema, stale health record and failed scheduled job may share one upstream release defect **or be independent**; only compare fresh revisions, actual unit hashes, supported schema, trigger times and detector evidence.
- **Engineering admission:** compare `SUPPORT-DEV-1440` + `SUPPORT-OPS-038/039/040/044/054` with [#1196](https://github.com/al-teamaot-com/jason/issues/1196), [#1493](https://github.com/al-teamaot-com/jason/issues/1493) and [#1304](https://github.com/al-teamaot-com/jason/issues/1304). They affect a related execution path but may require different fixes (reasoning HTTP contract, lost admission, blocked-slot accounting, stale installed worker).
- **False provider-health signal:** separate the Graph-client-scope canary record `SUPPORT-OPS-046` from a real Microsoft authentication outage until authoritative provider/tenant evidence supports escalation.
- **Self-heal correlation:** the second, colliding `SUPPORT-OPS-046` record already asks for grouping by a **violated operational invariant** rather than symptom names; coordinate under existing [#635](https://github.com/al-teamaot-com/jason/issues/635) without replacing its incident/repair machinery.
- **Customer troubleshooting exemplar:** [#1433](https://github.com/al-teamaot-com/jason/issues/1433) documents over 30 low-disk alert tickets related to one continuing disk condition. The same shared correlation principles can help prevent duplicate ticket storms, but **customer/client scope must remain separate from Jason-internal P0 incident identity**. Existing Resolution Memory [#951](https://github.com/al-teamaot-com/jason/issues/951) stores historical evidence and does not confer execution authority.

## C. Desired shared diagnostic contract (use Jason's existing services)

For each incident and symptom, record:

1. **Identity** — canonical incident UUID/fingerprint; exact organization/client/site/device/CI when applicable; domain (Jason production vs client endpoint vs security); original Support ID, ticket numbers, GitHub issues and persistent worker work IDs. Collision detection must preserve both `SUPPORT-OPS-046` records and must not invent a new authoritative Support ID.
2. **Symptoms & provenance** — detector, alert UID, first/last observed, time window, severity/impact, source SHA/version/host unit, observed facts with timestamps and freshness/TTL, contradicting evidence and unknowns. Existing `kernel` identity/tenant boundaries and orchestrator evidence sanitization are mandatory.
3. **Causal hypotheses** — candidate shared dependency, related symptoms/records, normalized failure/invariant, supporting and refuting evidence, confidence, and independent-cause alternatives; explicitly distinguish `same-incident`, `possibly-related`, `blocked-by`, `distinct`, and `unknown`. A plausible match is never a confirmed root cause.
4. **Decision and ownership** — one incident reference with zero or more linked symptom records; preserve **original** P0 priority, Owner sequencing, each issue's existing status/next action, and separate workstream/worker authority. Assign nothing based solely on text similarity.
5. **Resolution & verification** — record attempted approved fix and effect; re-run **every affected original detector** and appropriate upstream invariant/expected-state checks with fresh independent readback, stable dwell where appropriate, and explicit partial successes. Do not close sibling issues automatically based on one fix or close/merge across tenants.
6. **Learning** — upon verified outcome only, create/reuse Resolution Memory [#951](https://github.com/al-teamaot-com/jason/issues/951) with successful and failed steps, versions/targets and evidence references; historical fixes are hints, not standing authority.

**Algorithm preference:** deterministic exact identifier/tenant/resource matching and proven dependency edges first; use semantic/similarity matching only as candidate generation; require fresh independent evidence before causality or closure. Include negative cases for false positive correlation, different clients, reused IDs, unrelated upstream failures, device offline, stale versions, lost evidence, recurring/oscillating symptoms, concurrent repairs and failed notification.

## D. No-impact sequence and acceptance

| Stage | When | Allowed work | Exit check |
| --- | --- | --- | --- |
| 0: static P0 snapshot and requirements | **Now: DONE as staged documentation** | Read-only Support/GitHub inventory, identify ID collision and possible status divergence; cross-link existing owner issues | Keep `SUPPORT.md`, existing issue states, job scheduling and active releases unchanged |
| 1: reconcile with protected production evidence | After safe governed read capability is available; no production mutation | Read-only worker/Release Manager/controller evidence (if properly authorized); link per-detection and per-issue evidence; mark unverified as unknown | Defensible counts for distinct unresolved P0s, blockers, related symptoms and actionable vs stale status |
| 2: shadow correlation/parity test | After #1078, #1196, #1440/#1468/#1493 stability/acceptance gates and relevant #1069 control | **Existing** self-heal/ticket worker logic provides candidate links; compare to real historical incidents while preserving every original record and decision | Proven linkage precision, no hidden urgent issue, no false close, cross-client negative tests |
| 3: bounded gradual adoption | Only via existing approved TODO worker, separate scoped authorization, protected CI and governed Release Manager | Link/recheck original detectors after verified repairs; integrate Resolution Memory evidence and dashboards; feature-flagged canary and rollback | Two or more representative issues/symptoms correlated correctly, plus one falsifying unrelated case, one root-cause recheck, no duplicate action, fail-closed ambiguity |
| 4: continuous assurance | After independently accepted live behavior | Derive P0 counts and next actions from authoritative sources; detect orphaned/duplicate IDs, GitHub closure mismatches, recurrence and stale evidence | Every active P0 has honest owner/action/blocker; recurring unresolved root cause surfaces without introducing a second support/TODO engine |

**Non-interruption rule:** This documentation does not introduce a new P0, reprioritize existing work, create/close/move/support tickets, alter canonical Support IDs, dispatch a worker, trigger retries, change a release or approval gate, or authorize refactoring. Current Production Manager and Universal Teams Approver remain ahead of this initiative. Add relevant cross-references to existing #635 and #1535; implementation stays behind their existing gates.

## E. Governing references

- [SUPPORT.md](https://github.com/al-teamaot-com/jason/blob/main/SUPPORT.md) — authoritative recorded support backlog, **not an accurate live health oracle**.
- [#635](https://github.com/al-teamaot-com/jason/issues/635) — existing self-heal/incident correlation owner.
- [#1196](https://github.com/al-teamaot-com/jason/issues/1196) and [#770](https://github.com/al-teamaot-com/jason/issues/770) — engineering and ticket worker continuity; no competing queue.
- [#1078](https://github.com/al-teamaot-com/jason/issues/1078) and [#1440](https://github.com/al-teamaot-com/jason/issues/1440) — existing P0 non-interruption priorities.
- [#951](https://github.com/al-teamaot-com/jason/issues/951), [#188](https://github.com/al-teamaot-com/jason/issues/188), [#446](https://github.com/al-teamaot-com/jason/issues/446) — operational Resolution Memory, reuse only with current governance.
- [#1535](https://github.com/al-teamaot-com/jason/issues/1535) — shared-services adoption coordination after prerequisites; **not a separate incident engine**.
