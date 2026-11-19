# AOT Microsoft Graph Group Administration - Isolated Activation Candidate (2026-11-19)

## Scope
Enable only the existing AOT group pilot profile via `config/microsoft_graph/group-admin-release.json` and update the source-profile regression test. Do not change unrelated Autotask, ticket processing, PMv4, Microsoft Mail, SharePoint, or other provider behavior.

## Verified engineering evidence
- Current remote main baseline at preparation: `b44772f78fd71bc054f952967e1bd78bccf0b17c`.
- Running `jason-runtime` and `jason-mcp-pilot` revisions observed: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`; running ticket-core was reported healthy.
- Only activation profile and source-profile regression assertion were changed before this documentation artifact.
- Initial focused Microsoft group executor, authorization, catalog, bootstrap and release tests: 76 passed. Additional Graph group reader, preflight, pilot manifest and runtime tests: 18 passed; total 94 passed across two runs. MCP-specific test collection was not completed because the available host test virtual environments lack the `mcp` dependency; do not count these tests as passed.
- Group creation and membership remain unexecuted; existing production group capability registry reports zero active `identity_group` capabilities.
- The latest authority-health snapshot reported `status=pass`, `full_proof_status=pass`, `failures=[]`; this does not substitute for a current protected breaker/drift readback.

## Blocking production release constraints
1. The current remote main baseline differs from the running source by **612 files** (95,726 insertions / 258 deletions observed); a full runtime/MCP main promotion is **not isolated**. Prepare and independently validate a release mechanism or minimal backport that cannot replace or restart ticket processing, shadow gateway or unrelated services. Do not promote main as a shortcut.
2. Privileged metadata/readback for the four protected group OpenBao AppRole role/secret ID files is still required. A session command attempting privileged metadata inspection was blocked by remote command policy and was not bypassed. Root-protected production drift JSON was also inaccessible to the unprivileged account. Existing November 12 release evidence found root:root 0600; approved source contains a narrow `--prepare-runtime-access` command but it is not executed. Do not attempt local privilege bypass.
3. The protected breaker and production drift gate must be freshly verified and closed/clean before release. A passing systemd authority-health timer alone is not enough.
4. Build exact candidate and rollback images, review complete production-to-candidate dependency scope, run isolated preproduction and security tests, confirm source image revision and rollback, then obtain exact Owner release approval.
5. Only after governed deployment, obtain exact action approvals for one controlled group-create and one subsequent membership-add, each with Graph readback and ledger/audit evidence. No general production deployment approval is permission for Graph writes.

## Expected identities and boundary
- AOT tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`, client `client-aot-internal`.
- Dedicated group reader application `bb8f8e09-f851-4e0d-9c4a-95ff36d34b9a`; group writer application `6583ee4b-5aa7-4c82-a46e-472f03a4c467`.
- Group writes remain owner scoped with exact approvals; no Directory.ReadWrite.All or directory-role write expansion.

## Release acceptance and rollback
- Before/after: capture exact live image SHAs, container IDs, protected-core health, group registry state, group credential metadata, production breaker/drift, and no changes to unrelated services.
- Canary: AOT-owned ordinary security group; verify group ID/type/owner/name/alias and separately authorized direct member readback; no duplicate POST on unknown outcome.
- Failed checks: do not deploy or roll back through existing governed Release Manager; restore original freeze/holds, remove exactly four group-secret mounts and disable group profile, then verify core and authorization health.

**Status: Engineering candidate only; NOT approved, NOT deployed, and NOT production ready.**
