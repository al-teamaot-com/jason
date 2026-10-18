# P0 Release Manager preproduction clone: transient SQLite SHM race

**Parent:** #1078, #1440; source-only reliability defect. All release governance, exact owner authority, CCC, release breaker, and rollback rules remain unchanged.

## Observed incident

At 2026-10-18T12:38:59Z, the canonical installed Release Manager attempted an authorized **read-only/isolated preproduction preparation** of protected main revision `a11ae28b89878d41c3ed96d86231cf7d39297bd6`, after previous failed protected deployment `b1ea8751...` had been restored to the original production runtime/MCP/host SHA `ad11c311...` (independently aligned, but its rollback receipt remains FAILED).

The first isolated preparation built both exact-SHA candidate images, but failed `pre-production candidate failed health acceptance`. Canonical cleanup deleted the candidate preproduction container and scratch without preserving the underlying startup error. It remained `release_candidate`, `owner_approval.approved=false`, **not Production Eligible**. The generic health failure remains undiagnosed.

A single bounded canonical **preprod-only** retry at 12:43:14Z exposed a distinct concrete state-clone defect: `docker cp jason-runtime:/var/lib/jason/openclaw/governed-execution.sqlite3-shm` returned exit 1. The live SQLite shared-memory coordination file had been enumerated but disappeared before individual `docker cp`. No production mutation, approval, or deployment occurred.

## Bounded fix

The preproduction live-state clone already omits the very large `orchestration-events.sqlite3` event journal, WAL, and SHM as approved. This patch further omits **only top-level names matching `*.sqlite3-shm`**, because a SQLite WAL-index SHM file is regenerable ephemeral coordination state, is not a canonical committed database/WAL, and is unsuitable for sharing between live and isolated processes. Its disappearance is a normal SQLite lifecycle transition.

Critically, still clone each `*.sqlite3` database and `*.sqlite3-wal` write-ahead log, as well as every other valid production/authority/state entry. Missing databases or WAL copies still fail closed. Preserve all original directory-name/path validation, existing max 256 entries, 4 GiB copy limit, free-disk reserve, immutable source revision, provider mutation restrictions and cleanup-on-failure.

## Bounded preproduction failure diagnostics

The prior preproduction health failure was generic because canonical cleanup
removed the temporary container without preserving a readable startup state.
When all bounded health attempts fail, the source now reads only the isolated
container's Docker **status, exit code, OOM-killed flag, and health status** via
a bounded five-second inspect. It never captures Docker logs, environment,
mounts, customer data, credentials or arbitrary error output. If Docker state
is unavailable, it reports container_state=unavailable while still FAILING.
The old 30-attempt health check and all fail-closed cleanup behavior remain.

## Verification and completion boundaries

Isolated regression tests cover exact enumeration, retaining authority DB and WAL, skipping SHM, Docker-copy failure on a missing WAL, path validation and disk reserve behavior, in addition to existing Release Manager and protected gate tests. A passing code unit test does **not** establish the preproduction candidate healthy.

No attempt is made to hide, reinterpret or retry the original generic runtime-health error. A subsequent fully governed preparation of a new reviewed exact SHA must demonstrate successfully building candidate images, cloning state, *starting and health-verifying isolated runtime*, provider mutation guards, MCP/host preflight, and rollback readiness. If health again fails, log a bounded actionable diagnosis before proposing deployment. Once eligible, a separately Owner-authorized exact SHA and CCC review are required for any production mutation. High-risk owner-reviewed Teams mode and UTA remain OFF.

## Breaker readiness anomaly

The installed Release Manager's `prepare_release` currently invokes `revalidate_circuit_breaker`, even when owner approval is absent. At 12:39:02Z it triggered independent root `root_verified_revalidate` for old LKG `ad11c311...` and closed the breaker previously OPEN after `rollback_verified=false`. No human issued a separate manual reset. The transition was genuine root-governed manifest/drift revalidation, not a bypass or fake record, but this automatic closure **must not** be reported as complete verified rollback or operational Production Manager reliability. It merits independent constitutional review of whether ownerless preprod should change the production safety circuit, and remains separately tracked under #1078.
