# Governed catalog scoped v2: approval-capable images admission

**Lifecycle:** source-only eligibility evidence, not a deployment, release approval, or permission grant. The original production deployment freeze remains active.

## Why a v2 image is required

The first catalog-only read-only receipt, SHA256 `12c8fdeec4b3ffd361d06b40e51a94c8199dfb8f7b0bb30a6d7e6920defe9d31`, attested an isolated nine-file source (`d73f680864bd75cd714a89f36ae8a3190dc60e66`) and corresponding runtime/MCP images. The original MCP image did not contain the newly prepared exact-scope authenticated Owner approval tool. Reusing that receipt as though it attested newer executable code would be false. This v2 admission preserves the original receipt **unaltered**, with the original exact manifest frozen at `docs/engineering/evidence/catalog-scope-original-manifest-20261117.json`, SHA256 `dd2480eb01508c9f53180775644dfa0343a631d1d6452d265c7c937fbf32a239`.

## v2 source and candidate images

- Immutable production baseline and rollback source: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
- Source-only scoped runtime/MCP transaction PR: #2537 (merged protected source; feature SHA `565f388b0e72b0b2695d47ce146c9238de893948`)
- Exact v2 isolated source: `755fa5fe3f75958fee2427a0af0777dd242d8f00`, published ref `refs/heads/prep/catalog-identity-grants-owner-approval-isolated-20261117`
- Binary diff SHA256 against baseline: `d91998d980fc9b19105270e95067ded1a2068aaecf9ba59d5de642163dbc5ec9`
- Exactly **11** changed paths: previous nine catalog files plus `implementation/kernel/catalog_scoped_promotion_contract.py` and `implementation/mcp_service/src/jason_mcp/catalog_scoped_promotion_approval.py`, with one surgical catalog release-approval MCP server entrypoint change
- Runtime v2 image `sha256:dbd4d017dcc2deaf83109f5a0c6e68b3473c6de13881a56aa17238b647bbce66`
- MCP v2 image `sha256:da57dd05bfde19321ddb4eca2b1910aff41aee7027905365fdb76a12aa1989f2`
- Rollback runtime `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
- Rollback MCP `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- Original active freeze SHA256 `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`

The source verifier now requires **six** byte-matched catalog-only functions within the shared MCP server across isolated source, reviewed protected commit, and current protected main, plus **seven** whole-blob equality checks for catalog-owned modules and tests. The original baseline's other top-level MCP source nodes must remain unchanged, so unrelated PMv4, Ticket Core, security and other new functions cannot silently enter the isolated image. The verifier also requires exact scope hash, original rollback, rooted source ancestry, protected `main`, security CI and both immutable Docker digests.

## Verification already performed (no production mutation)

- Real Git history source verifier PASS: exactly 11 changed paths, six catalog function bodies, seven catalog source/test blobs, pinned v2 scope SHA256 `d91998...` against reviewed protected source
- Both v2 Docker images built from exact source `755fa5fe...`, both with matching source labels
- MCP image PASS in non-root, no-network, read-only sandbox: actual `approve_catalog_scoped_runtime_mcp_release` tool import and shared offer validator
- Both **installed** `deploy_live_container.py --preflight` checks PASS for v2 images, with exactly one dormant catalog setting each, original rollback image readbacks, no additional binds
- Source-only tests PASS: 438 native, scoped admission, transaction, Owner signer, rollback/recovery, root routing and bundle regressions plus 5 subtests. MCP Owner signer no-network tests PASS 12/12
- Original receipt is rejected as a **fresh** v2 receipt; only used as pinned predecessor. Source-only test fixture `tools/tests/catalog_scoped_v2_fixture.py` makes synthetic new evidence for offline adversarial tests only. It is never a real admission, Owner proof, release or provider record.

## Hardening found during source review

Follow-on source review discovered three trust-boundary issues and resolved them
before source release: (1) exact live protected security CI is rechecked inside
the root promotion transaction, not merely when an offer is staged; (2) the
native deploy helper is supplied from an exact-source, root-owned immutable
bundle rather than attempting to execute the group-writable live release copy;
(3) the root-only watchdog handles an interruption before the freeze backup
exists by verifying the original baseline without changing Docker, and opens
the breaker if that proof fails. The root breaker file remains root-owned mode
0600 inside the existing operator-owned 0700 Release Manager state directory;
a specialized, exact-path, root-only atomic writer honors that native layout.
The same protected root state and original freeze remain authoritative; this
does not create a new Owner or root-control authority.

## Completion gates

The v2 manifest update must become protected source with complete required CI before `catalog-scope-admit` can produce a **new real** read-only receipt. A source commit or a synthetic test fixture does not create a production-eligible release. Independently authorizing and installing root-owned Promotion Manager/worker/rollback components remains a **separate** governed production mutation and is explicitly **not authorized** in this source-only task. A new authenticated Owner exact-source/image/rollback release signature and separately approved Autotask test write/readback are also required. No independent human security-reviewer role is part of the project.

**No root installation, runtime/MCP replacement, freeze removal, provider credential switch, Autotask write or broad Owner allowlist change has occurred.**
