# PMv4 Stage A0 — exact one-file root source closure (source only)

**Status:** Engineering candidate. **NOT installed, approved, or executed in production.** This is distinct from the 14-file future-source regression in PR #2490.

## Verified incident / objective

The root-owned Stage A0 source at protected main `7b42ce983896711525de4c7955bf9fc43ac003d0` contains thirteen verified immutable files. The installed native loader also requires `tools/pmv4_host_install_contract.py`, a 9,571-byte Git blob with SHA-256 `ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db`. It is absent on the production root release path. Stage A0 correctly fails closed with `PMV4_NATIVE_INSTALLER_NOT_TRUSTED`.

## Source-only proposed helper

`tools/pmv4_stage_a0_root_source_closure.py` fixes the **existing pinned candidate only**. It requires all of the following before the exact one-file creation:

- Separately reviewed root-owned helper at `/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py`, launched in isolated Python as root; mutable source checkout cannot run as a privileged installer
- Root-owned immutable policy at `/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json` pinning the candidate, file and SHA, prior thirteen-file scope, proposal SHA, freeze, hold, runtime and MCP images, installed helper hash, original LKG and exact action
- Existing root-owned Stage A0 verifier, pinned Ed25519 Owner signer and independently verified fresh Entra OAuth Owner confirmation; no Teams requirement, secondary approver or new signer
- Existing root release lock; prior complete immutable thirteen-file scope readback; live breaker closed, fresh drift PASS, healthy protected runtime/MCP, unchanged current pointer/freeze/hold and verified protected-main CI
- Empty target (no replacement), root-owned 0700 empty one-use audit ledger, exclusive no-follow file creation with 0444 root metadata, fsync, exact readback and 14-file closure
- One-use attempt audit committed before target write; result audit and refusal on mismatch. The write helper retains an open original inode during rollback, avoiding inode-reuse deletion of a foreign replacement.

**Deliberate production boundary:** The helper is only source; it cannot install its own root-owned code or policy. The existing installed root worker does not expose a generic prerequisite-file repair action. Production bootstrap/activation needs a **separate authorized exact-scoped root transition** with independent review of candidate hashes, install mechanism, rollback and approval. Neither ordinary chat approval nor earlier consumed Stage A0 approvals suffice.

## Verified nonproduction checks

Run `python3 -m pytest -q tests/test_pmv4_stage_a0_root_source_closure.py`, along with existing Stage A0 and security regression suites. Tests verify fixed scope, real Git blob and thirteen-file baseline, exact exclusive copy, fail-closed source checkout, file tamper and symlink denial, conditional rollback and foreign replacement preservation.

Next engineering gates before any root installation: review code/security findings, prepare and attest exact root-installed helper and policy, independently verify full root trust/bootstrap, obtain authenticated exact-action Owner consent, and demonstrate disposable root-mode dry-run including injected failures and postflight. Production LKG, protected runtime/MCP, ticket processing, freeze, hold, and breaker must remain unchanged until separately approved.

## Exact policy review artifact (no live activation)

`config/pmv4-stage-a0/root-source-closure-policy-review.json` is a data-only reviewed example of the exact future trusted policy; it is **not** installed under `/etc`, is **not** signed, and grants **no production authority**. Its file hash and helper hash are verified by tests. The root-owned current policy remains separately inaccessible to the nonprivileged operator; any activation must independently read back current host state before consent and before write.

### Post-write rollback refinement

The production call now runs full fourteen-file closure verification and the unchanged runtime/freeze/hold health check **while the original created inode is still open**. If either check fails, only that exclusively created inode is eligible for rollback; a foreign replacement is preserved. An audit-result write failure after the write helper returns remains fail-closed and requires independent forensic readback; no unconditional deletion is authorized. This refinement is source-only and has not been exercised in the real root environment.

## Exact Owner-local trusted bootstrap, prepared 2026-11-15

A separate reviewed local root bootstrap has been prepared without generic sudo access or daemon changes. It installs **only** the fixed reviewed closure helper (root:root 0444), the fixed inert closure policy (root:root 0400), and an empty root:root 0700 audit ledger, after separate fresh Entra-authenticated exact-action approval and a root-owned one-use journal claim. The root consumer is **not** the mutable checkout; the local Owner launcher checks its immutable SHA before a root-only staged copy under a fixed `/run` path (0700 parent / 0400 file), then verifies the exact staged hash. The preapproved Python files are treated as SHA-pinned **data**, never arbitrary root executable imports. The current production runtime/MCP/freeze/hold/current pointer are not release targets.

- Action: `pmv4-stage-a0-root-source-closure-bootstrap-v1`.
- Reviewed source: protected main `7b42ce983896711525de4c7955bf9fc43ac003d0`, never changed by this source-only branch.
- Exact immutable plan in `/srv/jason/archive/pmv4-a0-closure-bootstrap-plan-7b42.json`; SHA256 `25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564`, scope SHA256 `e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb`.
- Source payloads: `/srv/jason/archive/pmv4-a0-root-source-closure-7b42.py`, SHA256 `1006edb6613f3ff976fadf64c25d8e6096dfef6b2296e4583ba51ee81ee4c4f6`; policy `/srv/jason/archive/pmv4-a0-root-source-closure-policy-7b42.json`, SHA256 `7cd1ef65c9bcf8c6442a191348ac187c05c421ed8576998b61b7427d08a5da32`.
- Existing approved root Ed25519 signer/verifier, immutable release control, native lock and fresh protected breaker/drift, runtime and MCP health are still enforced; no Teams approval or new signer.
- Owner-only consent script `tools/pmv4_a0_closure_bootstrap_owner.py` is source-only and writes at most a short-lived one-use signed proof under `/srv/jason/archive`. The root consumer `tools/pmv4_a0_closure_bootstrap_root.py` verifies this proof independently before any target write. It never auto-promotes a production release.
- The local wrapper `tools/pmv4_a0_closure_owner_local.sh --check-only` passes without root access or approval. `--execute` is reserved for a **real interactive local UID1000 Owner shell** with sudo: it requests **two distinct Entra exact-action confirmations** (first to install the fixed root helper/policy, then to repair the single protected root source file). It then verifies the repaired source digest and preserved freeze/hold/current pointer. **ChatGPT Remote Desktop Commander cannot execute this Owner-local sudo step.**
- Crucially, the subsequent **Stage A0 installation** remains a *different* signed Owner transaction via the already published Jason MCP `authorize_pmv4_stage_a0_install`; do not misrepresent the bootstrap+file repair as Stage A0 installation.

Do not run this against production unless the exact reviewed local bootstrap package and the separately authenticated Owner/root conditions pass. A chat approval alone cannot replace the signed Entra proof. Root/mode/rollback acceptance must pass in disposable UID0 CI (no production mounts) and live state must be revalidated immediately before execution.
