# PMv4 Stage A0 — native root source dependency-closure repair

**Date:** 2026-11-14

**Status:** VERIFIED production defect; **source-only corrective proposal**; no root repair/release authorization in this record.

**Protected source SHA:** `7b42ce983896711525de4c7955bf9fc43ac003d0`
**Prior 13-file stage scope SHA256:** `09e35bf812c3bedd61991af669ea9a80b0a0ff5948b1d1a6edb1d70c3332c27f`

## What failed, and what actually passed

The authenticated Owner MCP tool `authorize_pmv4_stage_a0_install` became callable in the live ChatGPT session. It verified the Owner Entra bearer, exact candidate/source/manifest/freeze and affirmative decision. Two one-use requests were accepted at the trusted MCP boundary and independently processed by the installed root reconcile worker:

1. `2026-11-14T18:31:11Z` — root result `requested host release is not on protected origin/main`. The managed **unprivileged** root worker Git mirror had a stale `origin/main` reference `323ac1827cfe375bd58aa4f487400b911f8d23aa`; GitHub and the separate engineering checkout already pointed to `7b42ce9...`. The existing `ReleaseManager.ensure_managed_host_source_revision()` successfully refreshed **only** that managed mirror to current protected main without changing its LKG HEAD, container, freeze or hold.
2. `2026-11-14T18:33:30Z` — fresh exact Entra-authenticated request accepted; root progressed past protected-main ancestry, then failed closed with `PMV4_NATIVE_INSTALLER_NOT_TRUSTED`. The worker's `_trusted_native_stage_a0_module()` requires **nine** pinned root source modules but the earlier explicitly approved sparse root staging installed only **13 files** and omitted one required module.

**Missing root dependency:** `tools/pmv4_host_install_contract.py`, exactly 9,571 bytes, Git SHA256 `ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db`. It is present in the approved protected main source and is imported by `tools/pmv4_stage_a_packet.py`, but it was **absent** from `tools/pmv4_stage_a0_sparse_source.REQUIRED` and from `tools/pmv4_stage_a_packet.ROOT_STAGE_A_REQUIRED_SOURCES`; the root loader's `required_modules` did correctly require it. The worker correctly refused loading root code that could depend on mutable, operator-owned Python.

The previously approved 13 source blobs were independently read back root:root/0444, each digest-matching its approved original manifest and with no foreign files. The installed native module under `/usr/local/lib/jason/pmv4_stage_a_native_install.py` matched the same protected Git blob byte for byte. Therefore **do not alter** the installed root worker's trust/ownership/source checks or import an al-writable module as a shortcut.

## Source-only durable correction

This separate draft branch adds the omitted path to:

- `tools/pmv4_stage_a0_sparse_source.REQUIRED` so a newly approved, future exact sparse source bundle includes fourteen files;
- `tools/pmv4_stage_a_packet.ROOT_STAGE_A_REQUIRED_SOURCES` so the root transaction independently attests its exact Git blob;
- the future root source stage's **new v2 exact-action identity**, `install_scope` label and disposable tests, which deliberately change from the existing v1/`only-13-...` to v2/`only-14-...`. The currently installed v1 root stager and its consumed one-use policy are never silently repurposed.

New `tests/test_pmv4_stage_a0_sparse_dependency_closure.py` parses the root worker's actual required module tuple using Python AST and makes every required module a subset of the sparse source allowlist. It proves the transitive packet import file is within the fourteen source files, the new archive includes its pinned digest/root metadata, and a formerly approved thirteen-file manifest cannot validate as the new fourteen-file scope. Original 13-file production approval remains consumed and **cannot be silently enlarged** by this source PR. Protected main and running root code remain unchanged.

## Exact remediation plan for the existing protected Stage A0 candidate

The currently installed root source tree remains at `/opt/jason/releases/7b42ce983896711525de4c7955bf9fc43ac003d0`, with exactly thirteen reviewed immutable files. A targeted remediation packet was prepared on the host:

`/srv/jason/archive/pmv4-stage-a0-root-source-closure-repair-proposal-7b42ce983896711525de4c7955bf9fc43ac003d0.json`

Its canonical proposal SHA256 is `089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381`. It explicitly marks `production_apply_supported=false` and `root_mutation_authorized=false`: it is **evidence, not authorization**.

The narrow governed recovery action, *if separately authorized*, is:

1. Authenticate Owner against current Microsoft Entra and obtain exact-action approval for **only** creating `/opt/jason/releases/7b42ce983896711525de4c7955bf9fc43ac003d0/tools/pmv4_host_install_contract.py`, root:root/0444, from its protected Git blob digest above. No root code is taken from a mutable working directory.
2. The native root controller independently holds the existing production release lock, validates root LKG/current pointer, closed breaker, fresh drift PASS, both freeze/hold SHA256s, original thirteen-file sparse source manifest/content/ownership/no foreign files, protected Git main and the new one-file blob digest. It must refuse an existing file/symlink, unreviewed target, changed content/owner/mode, or an unavailable journal.
3. Create **one** root file with no-follow, exclusive creation, fchown/fchmod and fsync. Write a root-owned append-only/replay-safe exact-action receipt; on a failed/unconfirmed write, remove only its own exactly matching newly created inode, never any foreign data.
4. Confirm the complete fourteen-file source closure against protected commit and root loader, no container restart, no ticket runtime change, unchanged freeze/hold/LKG. Only then issue a **fresh separately authenticated** Stage A0 one-use request via the already working MCP tool, and independently inspect its final root install receipt and the Stage A0 expected root artifacts.

**Authorization boundary:** The currently installed root worker only accepts the original Stage A0 transaction and cannot install a new prerequisite file on the basis of that original approval. This draft does **not** install or expose a new root dependency-staging action. Applying the targeted root repair requires a separately reviewed Owner-authenticated root transition using existing trusted signing/lock/audit safeguards, or a separately governed root helper release. Do not substitute `sudo cp`, `docker exec`, a manually writable checkout import, a repeated consumed approval or a generic production release.

The next Stage A0 native scope remains `6786baad0fc9d07aca6ba80dedad5c25bcfa7fb3e50fdde7c4d36ad067285eac`; the native install manifest SHA256 remains `addba768d1ab92d9507d466fdd3980b93ea2041f42901f5d6e5a2cde81dcb025`. That native scope describes a different **create-only Stage A0 target namespace** and does not itself authorize the prerequisite source-tree change.

## Verification and disposition

Focused current worktree acceptance: **76 passed, 8 skipped**. This includes a real **`python -I` disposable temporary-directory import** of the complete fourteen-source-file native root graph (never calling the installer), which passed and will catch a missing transitive Python module in addition to the independent AST source allowlist check. Run all applicable repository CI/security checks and disposable real-root staging tests with no production paths before release approval. After adding a supported exact-source closure root transition, test malicious source blobs, hardlink/symlink substitution, injected extra files, interruption, duplicates/replay, stale current main, Owner identity mismatch, revocation, policy drift, and rollback.

Until the missing root source is properly repaired, the following are **NOT complete**: Stage A0 native installation, PMv4 shadow, independent Ticket Core, independent Runbook Management, formal one-approval policy deployment, and PMv3 retirement. Preserve protected `origin/main` source pin and production freeze.

**Operational Owner experience:** Do not present raw MCP parameters as Bash commands. The ChatGPT/Jason MCP tool itself is now published and works; the remaining blocker is the separate root source packaging defect, not user skill, ChatGPT connectivity or an OAuth login failure.
