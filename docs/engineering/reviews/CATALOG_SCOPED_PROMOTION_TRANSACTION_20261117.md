# Catalog-only dual-image promotion — governed source-only engineering

**Date:** 2026-11-17. **Authorized:** source-only implementation and testing; no production deployment, root installation, service restarts, global unfreeze, provider mutation, or new Owner privileges. **No independent human security reviewer is required**; existing protected CI, root trust and authenticated exact-action Owner approvals remain mandatory.

## Objective

Use the already verified read-only catalog admission receipt `12c8fdeec4b3ffd361d06b40e51a94c8199dfb8f7b0bb30a6d7e6920defe9d31` as immutable predecessor evidence, then promote exactly the catalog-only Jason runtime and MCP images under the existing Production Manager. The original correction is merged as PR #2515 and the self-only Owner catalog grant administration is merged as PR #2522. The read-only admission gate is merged in protected source PR #2528.

The original snapshot `d73f680864bd75cd714a89f36ae8a3190dc60e66` is based on live production `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`; nine changed files, binary scope SHA256 `574361739ef89969a22932a9cb8731432b9b715a5a0a78fbdbd66d79a2494256`. Its runtime image `sha256:98f5d3f4a16e55b9a49fa424056dc30a8139dc443f4948d2aaf524ac4fa9dddf` and MCP image `sha256:ea8a3fca67b9f75dbd2ec4156cb8d1a657c13efd72886b4d16e54046070de9b9` have passed offline smoke/preflight, but **neither has been promoted**. Existing rollback runtime `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132` and MCP `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477` remain live, aligned to the original source. The freeze SHA256 is `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.

## Code boundaries

- `tools/catalog_scoped_promotion.py` implements exact immutable offer/receipt verification and the two-image state machine. It cannot deploy without a separately hash-pinned installed native host implementation, authenticated signed Owner proof, native lock, root control and explicit rollback.
- `implementation/kernel/catalog_scoped_promotion_contract.py` is the shared, pure offer-validator available inside MCP without depending on Python tools from a developer checkout.
- `implementation/mcp_service/src/jason_mcp/catalog_scoped_promotion_approval.py` and the dedicated `approve_catalog_scoped_runtime_mcp_release` MCP tool reuse existing Entra Owner authentication, tenant/subject binding, pinned Ed25519 signing key and original signed release proof. The only action is an affirmative, one-use exact-signature request for the fixed candidate, rollback, scope, manifest and freeze. No call to Autotask, Docker, unfreeze or production approval is made by merely viewing the offer.
- The existing MCP container has a writable `/var/lib/jason/authority` mount, **not** the Release Manager state root. The Owner exchange therefore uses only `/var/lib/jason/authority/catalog-scoped-release/{offers,owner-approvals}`, installed and checked with uid/mode constraints. This does not introduce a new wide provider mount.
- `tools/release_manager_host_runner.py` adds three typed Production Manager commands (`catalog-scope-stage`, `catalog-scope-promote`, `catalog-scope-recover`). They validate exact source and offer, require the installed native root worker, and enqueue a bounded request. They do not accept `--owner-approved` flags or directly run Docker.
- `tools/release_host_reconcile_worker.py` adds three exact-request actions (no arbitrary command, environment, runtime, file path or provider parameters). It validates al-owned mode-0600 requests and independently checks protected main. Before importing root code, it checks every executable blob in the separately installed root-owned immutable bundle against the protected exact-source commit. The existing host-reconcile/PMV4 routes retain their original boundaries.
- `tools/catalog_scoped_promotion_host.py` implements the root-owned native implementation: production transaction lock, current root breaker and independent drift proof, original freeze readback, immutable dual images and source labels, one-use Owner consumption, rollback-by-retained-original-container, protected container snapshots, source-scoped control readback, original frozen state restoration and root breaker opening if rollback or freeze cannot be verified. It refuses execution from any mutable worktree.
- `tools/catalog_scoped_control_readback.py` verifies that the original host release and protected last-known-good stay unchanged while only `jason-runtime` and `jason-mcp-pilot` are on their reviewed scoped image digests. It does not broaden the standard full-main release path or pretend the host source equals the isolated runtime SHA.
- `tools/catalog_scoped_promotion_recovery.py` and the source-only systemd service/timer provide bounded post-interruption rollback/steady-state checks. Promotion refuses to run until root installation, timer activity and root source digests have been independently confirmed.
- `tools/catalog_scoped_promotion_bundle.py` creates an unprivileged, exact-commit source staging copy and hash manifest; it is deliberately incapable of installing or starting production code.

## Governed one-transaction sequence (future, NOT authorized now)

1. Source merged into protected main; all required CI including SEC-007 pass. Independently build and verify a **new isolated candidate** containing the approval issuer and shared kernel contract, because the older MCP image `ea8a...` was built before the new issuer existed. Re-attest exact immutable candidate images; keep receipt `12c8...` as predecessor evidence. Do not mislabel an older image with newer source.
2. Separately authorized installer stages the exact immutable root host-worker/code bundle and policy, with root ownership/digests, current production lock, complete rollback scope, automatic recovery watchdog active, root protected control-readback support and the existing provider secret mounts preserved. Merely merging source does not install it.
3. Using the installed Production Manager, stage the exact root-owned offer with current protected Git/CI and fresh admission. The Owner can inspect the immutable source, both images, rollback, SHA256 scope, freeze and exact manifest.
4. An authenticated Owner explicitly signs the one-use exact offer. The signed request binds Owner Entra tenant/object, signature, fresh time, release ID, candidate SHA, rollback SHA, scope SHA256, manifest SHA256 and freeze SHA256. Root independently validates the original public key and replay ledger. Ordinary chat text, caller identity spoofing and a shared Owner allowlist change are insufficient.
5. The root worker, holding the **existing** native serialized `production-transaction.lock`, independently revalidates protected source/CI, healthy original runtime/MCP, host source, root breaker, freeze and rollback images; journals the exact intent and consumes the signature durably **before** removing the freeze marker for one bounded transaction.
6. Replace only `jason-runtime`, then `jason-mcp-pilot`, through the existing native Docker hardening script, each with **one** new configuration item: runtime `JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed` and MCP `JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE=aot-catalog-self-owner-v1`. No new credentials, global Owner impersonation, unrelated feature activation or broad `main` deployment.
7. Independently read back both live images, source labels, hardening and health; verify `jason-pmv4-shadow-gateway`, `jason-teams-gateway` and `openbao` have unchanged container identity/start time/image. Publish only the exact reviewed root scoped overlay. Restore and verify original freeze bytes, ownership and hash.
8. On any failure, restore both preserved original containers, original host pointer, original protected services, remove pending overlay, verify exact health/freeze and record an immutable failure receipt. Unverified rollback or freeze restoration opens the protected breaker and requires human recovery. A root-timer recovery route may rollback an interrupted previously approved attempt; it never reuses the Owner proof to promote again.
9. After verified production, separately authorize a named inactive, nonbillable Autotask service create; read back every provider field and verify no `ImpersonationResourceId` on the four catalog operations, with human caller attribution. Cleanup or any other provider mutation requires its own approval.

## Explicit controls and installation boundary

**No root module, systemd unit, MCP issuer or promotion command in this branch is installed or activated.** A production freeze remains active. Existing root release-control source must not be silently replaced with this checkout. The root state and trusted policy must be staged only by a separately approved installer from a protected, exact-source, source-pinned package. The source-only package does not constitute an installation receipt or production eligibility. The automatic rollback watchdog requires a separately approved root policy/desired-state allowlist update and signed installation; until its status and hashes are independently verified, the root-host adapter refuses promotion.

The first verified receipt covers the old 9-file candidate. **It cannot by itself authorize a new MCP image containing the Owner approval tool.** A follow-on exact source/image admission receipt is mandatory before any executable release offer; the old receipt remains immutable predecessor evidence, not standing permission.

## Nonproduction v2 image candidate (verified, not yet admitted)

The precise missing-Owner-tool gap was resolved at the **isolated build** level
without changing production: source snapshot
`755fa5fe3f75958fee2427a0af0777dd242d8f00` is a descendant of the
original isolated snapshot. Its diff against the running production baseline
has **11** source paths and binary SHA256
`d91998d980fc9b19105270e95067ded1a2068aaecf9ba59d5de642163dbc5ec9`.
Only the new MCP Owner issuer, pure kernel offer contract and its one source
tool registration were added relative to the previous catalog snapshot.
The new runtime and MCP image identifiers are respectively
`sha256:dbd4d017dcc2deaf83109f5a0c6e68b3473c6de13881a56aa17238b647bbce66`
and `sha256:da57dd05bfde19321ddb4eca2b1910aff41aee7027905365fdb76a12aa1989f2`.
Both images were built with exact 40-character source labels, and both passed
the **existing** native deployment-script `--preflight` using one new scoped
environment setting and no new read-only binds. The MCP image independently
passed an unprivileged, no-network import of the signed Owner tool.

**These are not yet production-eligible images.** A current protected-source
scope admission must bind the v2 source and images and explicitly consume the
original verified read-only receipt. Neither the original admission nor the
source code merge is an exact-action production release approval.

Integration coordination: #2456, #2525, #2527. #2456 edits the unrelated
read-only Datto numeric identifier projection in the shared MCP server near
the beginning of that module. This change adds an Owner-signed catalog release
tool near the release approval functions. The reviewed functions do not
intersect and no #2456 code is pulled into the frozen catalog snapshot.

## Verification

All tested actions use a source worktree, fake root adapters, disposable temporary directories, no-network/non-root Docker test harness for MCP and no provider secret. Tests include forged Owner tenant/object, wrong/expired/used signature, scope or image drift, extra service or environment field, modified freeze, missing root installer, outsider untrusted request, partial Docker rename/crash, both-image rollback, unchanged protected service IDs, and failure to restore freeze. Tested integration is source-only. A local test pass does not claim a live root installation, native promotion, or provider write.
