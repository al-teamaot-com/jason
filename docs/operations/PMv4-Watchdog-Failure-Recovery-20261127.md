# PMv4 engineering and self-heal failure recovery — November 27, 2026

Status: **source-only exact successor; not deployed or approved**.

## Live incident and cause

The root acceptance for c4e78d700b7ac347e9dee50c750d5de99780e2a2
verified two normal scheduled cycles at 02:00 and 02:05 EST. At 03:06:01
EST the watchdog's read-only Git status probe exceeded ten seconds and
escaped its Docker-only timeout handler. The watchdog unit failed. At
03:10 both services began rejecting the peer's failed state as if the
sandbox itself had changed. Their four systemd unit files still match the
accepted receipt byte-for-byte. The real sandbox properties also match.
The authoritative drift watchdog reports exactly the two required failed
system units and correctly holds the breaker open. The live runtime, MCP,
Ticket Core, Teams gateway and OpenBao remain protected. Do not clear the
breaker by changing its ledger or downgrading the required units.

## Exact repair

* Keep the existing root-owned manager receipt, immutable artifact pins,
  UID, cgroup, systemd sandbox, old-user retirement and native drift checks.
  Distinguish a failed peer's operational state from an actual sandbox
  change. Only the actual scheduled self-heal service can enter diagnostics
  with its exact quiescent engineering peer failed. External status and
  engineering admission remain strict. No root start authority is added.
* Suppress existing host/storage repairs whenever strict routing or the
  engineering source probe is inconclusive. The read-only Git probes are
  bounded; optional Git status locks are disabled. Only the exact known
  read commands may be classified inconclusive; unknown/mutating timeouts
  remain errors. Keep the detector's normal bounded retry and incident ledger.
* Reuse the existing signed native manager transaction, rooted at the
  accepted c4e78d70 predecessor. A recovery preflight attests the actual
  failed pair and every immutable predecessor pin, and independently checks
  that the authoritative and freshly evaluated native drift report exactly
  these two faults. The installed drift reporter exits 2 after correctly
  recording drift; its own subsequent failed-unit flag can therefore appear
  in a separate read-only evaluation. The authoritative drift list must
  still contain exactly the pair. Only with the pinned reporter program,
  unit and drop-in bytes and exact systemd failed/exit-code/2/zero-PID
  evidence may the independent evaluation contain this one derived record.
  No other fault is admitted, no recorded evidence is rewritten, and no
  additional reset or stop is authorized. Native revalidation must still
  obtain an actual unqualified drift pass. It does not represent the failed
  manager as ready.
  Check the protected runtime LKG, native core/ticket health, accepted
  audit recovery, existing no-paid-AI configuration and unchanged freeze/hold.
* Once exact protected source and CI are attested, one independently
  authenticated Owner action records the complete scope and original file
  images. Preserve the pre-cutover failure evidence before mutating. Stop
  only the two existing timers, quiesce both failed oneshots, install the
  exact reviewed worker/guard receipt and immutable source bytes. Reset only
  those two failed states, restart only their timers, and verify strict
  native guard/sandbox, existing native breaker revalidation, and full
  protected health before releasing the existing engineering pause.
* Include the already merged local-reasoning host workers from PR #2762:
  support, owner-approved development and supervisor. The previous owner
  worker receipt pin remains valid for historical releases; the successor
  binds the exact new worker hash. No old credit receipt is replayed. No
  application runtime/MCP image or model configuration is installed by this
  host repair. Local reasoning remains unaccepted until its separate
  exact native runtime release, fresh real runtime diagnostic and actual
  worker advancement. No paid model call or credential is authorized.

## Acceptance and rollback

The existing scoped release transaction retains its immutable Owner evidence,
original file images, two native mutation locks, exact target paths, protected
peer identities, prior Stage E acceptance, and rollback to the predecessor
with engineering paused on failure. The known fault is an explicit,
one-time host-recovery precondition, not an exception to ordinary production
promotion. No new privileged caller, policy change, root service, provider
write, global reset-failed, container restart, production image replacement,
freeze change, or native breaker override is authorized. The existing
breaker recovery mechanism alone verifies and closes the breaker.
No operational success is inferred from the preflight.

Tests must exercise positive and negative exact failed-pair evidence,
changed sandbox/UID/drop-ins/running PID, stale/unrelated drift, authority
and target expansion, historic and new receipt pins, bounded Git read
timeouts and actual nonmutation. Production acceptance remains two distinct
normal scheduled full cycles with native drift PASS and closed breaker,
fresh watchdog engineering-progress evidence, conflict quarantine,
unchanged protected peers, no paid calls, and protected core ticket
continuity. This is not proof that the original autonomous-engineering
stall has cleared; that requires actual local reasoning runtime acceptance.

## Risk classification

This is a correction to the already authorized manager's failure handling.
The diagnostic-only watchdog path grants neither a new identity nor any
mutation authority. The native one-time host-repair preflight binds exact
faults, reviewed source, unchanged protection/locks, Owner scope and rollback.
It does not weaken ordinary release admission or close an open breaker.
Security and governance reviewers must verify these invariants; source
tests are not an independent human security approval or production acceptance.
