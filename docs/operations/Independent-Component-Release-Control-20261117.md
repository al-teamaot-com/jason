# Governed Independent Component Releases — Source Contract (November 17, 2026)

**Lifecycle:** engineering candidate only; NOT INSTALLED, NOT ACTIVATED, NOT AN OWNER RELEASE RECEIPT.
**Scope:** a reusable, independent, one-Compose-service release transaction outside the existing PMV3 runtime/MCP and PMv4 shadow release paths.
**Constitution:** Project Jason Canon and governance, PMV3/PMv4 protected-source release policy, Jason Governance Simplification (2026-11-10), signed Owner exact-action proof, least privilege and fail closed.

## Why this exists

The existing native Release Manager builds/promotes the shared runtime and MCP. It cannot safely execute an approval that explicitly authorizes only a separate financial-statement Compose service. An ordinary shell or Docker operation would also ignore the active Owner-ordered production freeze. This mechanism is a distinct *component-only* transaction that reuses Jason's authenticated Owner proof, protected host locks and protected-service health checks. It does **not** change the behavior of the existing release managers.

The initial reviewed component is the financial-statement scheduler; later components must add **separately reviewed root host profiles**, not introduce arbitrary Compose CLI arguments or acquire standing approval.

## Source files

- `tools/independent_component_release.py`: strict manifest/scope/bundle verification, exact tenant/client/provider boundary, signed Owner verification, root-owned ledger, protected-service continuity, exclusive component transaction, component-only rollback and interrupted-transaction reconciliation
- `tools/independent_component_host_adapter.py`: root-only host callback implementation; validates resolved Docker Compose to one approved service, exact image and approved role/config/boundary/state mounts; uses the *same PMV3 and PMv4 lock inodes* through the independently trusted host guard; reads the protected control/CI state; never deploys any second service
- `tools/independent_component_release_root.py`: pinned root entrypoint with only `promote` and `recover-interrupted-rollback`; rejects development/worktree execution
- `implementation/mcp_service/src/jason_mcp/independent_component_release_approval.py` and new `approve_independent_component_release` MCP handler: authenticated Entra Owner-only, 15-minute one-use Ed25519 approval bound to the exact immutable candidate, scoped manifest, rollback, freeze fingerprint, and reviewed image. A signed receipt is *only* a request, not deployment
- `config/independent-component-host-profiles.example.json`: source-only initial component profile; not production host configuration
- `docs/operations/independent-component-financial-candidate-20261117/{manifest.json,scope.json}`: source-only exact financial service candidate, NOT root-staged for production

No new root service, timer, systemd unit, Compose project, credentials, signing key, unfreeze token, or production authority is installed by this PR.

## Exact first component (Owner-approved immutable service stays unchanged)

- Service source: `c205bb4ac163e7d433796f2f4839a90c7cc1f56b`
- Immutable image ID: `sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195`
- Enabled config digest: `42e5f9bdc891bc1cc9e7ee92cc48f08c7764eec619d62b311ee10bd62ac68310`
- Compose digest from approved source: `2b0ba17c4b813f9c8b7bd29f9955b6a9a387016fe1a3c08611ec582033c8447f`
- Validated one-site boundary snapshot digest: `be0dcf36c442040d586237e0eed184e7596f7fa94d23728f82ad28246ccdde66`
- Snapshot includes exactly `client-aot-internal`, `microsoft_sharepoint`, profile `sharepoint-write`, AOT Entra tenant, app `3d362478-a873-4ba2-b8a5-c04e66ef2f32`, and the exact `AOTAccountingDocuments` site ID
- Freeze marker digest observed during preparation: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`
- New component-only reviewed scope SHA256: `ee36d69187b2b0aabb6ba19521c48adde71af95d5e8621855b590a5c03755f9c`
- New component-only manifest SHA256: `56d7b12c6ee716e522aac66323fe59258256542ba6e6d104182807e3d7ec638e`
- Schedule: local `05:00 America/New_York`; real scheduled filing, readback, audit, duplicate preservation and idempotence have **not** been verified in production

The original Owner approval of the financial image is preserved. It **does not** prove an already-consumable cryptographic approval for this *new* manifest. A fresh authenticated, exact-manifest signing event is required only when the native component transaction exists and all release gates pass.

## Trusted host installation contract — SEPARATELY GOVERNED

Only after a *new separately approved exact-SHA release-control installation* may a trusted installer create:

1. `/opt/jason/independent-component-release/trusted/tools/` with the three controller/adapter modules and pinned, independently reviewed dependencies (Kernel signed-release verifier, host lock guard, cryptography, PyYAML). Root-owned immutable regular files, not symlinks, and parent directories not group/other writable.
2. `/etc/jason/independent-component-release/host-profiles.json`: root-owned, read-only exact reviewed profile, independently pinned to the allowed project, OpenBao role/secret files, network, and component state directory. The example is **not** authoritative until installed under the governed release transaction.
3. `/var/lib/jason/independent-component-release/`: a new root-owned 0700 control tree with root-owned immutable candidate bundles under `releases/<approved-sha>/`, `receipts/`, `active/`, and `control/component-release.lock`. Review and pin the actual component-manifest, reviewed-scope, Compose, config and **one-boundary-only** SQLite bytes before making them root-owned immutable.
4. `control/protected-ci.json`: root-owned verification attestation generated by a separately authorized live GitHub protected-main/required-check attestor. An assertion invented in chat or copied from old CI is not acceptable; this file must be freshly regenerated and independently verified shortly before admission.
5. Authenticated MCP release-only approval offer in the existing release manager's shared state; the Owner handler signs only a fresh, independently prepared `production_eligible` component offer. The root entrypoint reads only the fixed approval-outbox path and independently verifies the actual signed payload against the pinned root public key and root-owned bundle. It does not trust unsigned outbox metadata.
6. The existing PMV3 legacy transaction lock and PMv4 independently owned host lock must be acquired together for the **entire** component preflight, provider activation, verification and rollback. Current protected breaker/health must be independently verified closed and no parallel host mutation admitted.
7. The active Owner freeze must match the signed exact fingerprint. The component transaction is a one-release, scoped exception **only if the newly installed root policy explicitly authorizes that exact action**. The legacy freeze marker is kept byte-identical on success/failure and is never deleted, globally disabled, or extended by this source change.

**Important:** Releasing the MCP approval handler itself affects a separate production MCP surface and requires its own governed release-control authorization. The new source endpoint is not present on the deployed MCP until that separately approved transaction has occurred. No direct Worktree Python call, `sudo docker compose`, or direct mutation of `/var/lib/jason/authority/client-boundaries.sqlite3` is an authorized substitute.

## Release sequence after separately approved root installation

1. Independently verify candidate source against protected `main` and all required CI; build/install **exactly the previously accepted image**, never rebuild under a mutable tag.
2. Verify currently installed runtime/MCP/PMv4/OpenBao container IDs, images, starts, health; capture fresh authoritative production control/breaker state and global release lock readiness.
3. Pin the exact root-owned component-only bundle and reviewed site scope. Verify the boundary sqlite integrity, exactly one validated client/tenant/application/site record, and no onboarding transactions. Do **not** point the component at the live runtime authority DB.
4. Verify the approved image provenance label and resolved Compose *after interpolation*. Reject any extra service, build, privilege escalation, unexpected network or mount, or non-immutable image.
5. Generate one independently verified `production_eligible` component approval offer. Through active Entra OAuth, the Owner signs **one** exact SHA, approved image, scope/manifest/freeze/rollback action. The private signer remains in the existing restricted service; never print, copy or pass it through chat.
6. Root controller revalidates all proofs while holding both host locks and its own component lock. Create an exclusive durable `started` receipt before the first component mutation. Activate ONLY that Compose service. Check running image and original protected container IDs/start times, and preserve the production freeze byte-for-byte.
7. On any failed acceptance, stop/remove or restore ONLY the component using its previous immutable release; independently recheck all protected services; preserve state/audit; mark `rolled_back` only if readback passed. Any interrupted or failed rollback remains `started` and blocks further release until authenticated prior-transaction reconciliation. Do not run a second instance of the financial scheduler.
8. Separately verify the next real scheduled 05:00 Eastern run, actual provider-file readbacks, immutable audit chain/canonical event sink, preservation of ambiguous and duplicate files, and subsequent no-change/idempotent behavior. Until then operational completion is **not** 100%.

## Change boundaries and explicit stopping conditions

The following are never permitted by this controller: starting or recreating `jason-runtime`, `jason-mcp-pilot`, `jason-pmv4-shadow-gateway`, `openbao`, `jason-teams-gateway`, or an unrelated Compose service; modifying the runtime authority database; global freeze removal; setting `enabled=true` except by pinning the reviewed config; creating additional site permissions; fallback to a personal/delegated Microsoft identity; disabling root/public-key checks or faking CI evidence.

Do not promote if the source has not passed required CI, the candidate changes, the freeze digest differs, the Owner proof is absent/expired/replayed, a protected container changes, the root installer is absent, a mounted file is mutable/untrusted, the previously approved image is missing, a circuit breaker is open, a transaction lock is occupied, or rollback is unverified.

## Test acceptance and outstanding production dependency

Unit/failure tests cover manifest and scope drift, wrong tenant/site, Compose escalation, signature expiry/replay/tamper, freeze drift, host-lock contention, one-service command construction, failed deployment rollback, protected runtime drift, interrupted rollback recovery, and inability to invoke the production controller from a source worktree.

**Not a production acceptance claim:** CI and preproduction tests establish source correctness. The trusted root installer, protected CI attestor, Owner-signed component release offer, and first actual 05:00 operational run are *separate* installation and operational boundaries. They have not been executed in this engineering-only scope.

## Active integration coordination (2026-11-17)

- PR #2522 adds an opt-in, catalog-only exact-grant administration helper and modifies the existing `list_exact_authority_grants` / `grant_exact_authority` portions of `implementation/mcp_service/src/jason_mcp/server.py` around lines 4367–4672. The independent-component change adds a separate `approve_independent_component_release` tool near the existing release-approval tool around line 5330, and retains the existing `_release_approval_owner` verification. There is no overlapping function; when #2522 merges, preserve its catalog-only restrictions and this release-only Owner authorization without extending either.
- PR #2456 extends `_project_endpoint_read` for exact Datto device identifiers around line 841. This is a different function and provider-read projection; the component-release source does not modify endpoint reads. Preserve both independently when integrating.
- **Integration coordination: #2522 #2456** is acknowledged only after reviewing those exact patches. This is not approval to merge either change or enable any catalog/Datto capability. Re-run the required integration/security checks if either merges before this PR.

