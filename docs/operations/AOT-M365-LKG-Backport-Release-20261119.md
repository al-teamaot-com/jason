# AOT M365 group administration - protected LKG minimal backport candidate

## Release purpose
Enable ONLY the already engineered AOT Microsoft group pilot (group create and direct member-add under exact-action approval), on top of the existing running protected runtime revision `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. Do NOT include the 612-file latest-main migration delta or unrelated PMv4, ticket, Autotask, SharePoint, financial or procurement changes.

## Source and implementation
- Base exact protected LKG: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Reviewed source feature: original Group Admin PR #2454, base `387063db0c1f633529b3ecb6920da6a72a64dc03` -> head `7498c0968afb52a8d7506f9dc8ad1fd981ef35e5`.
- Applying that 38-file feature patch to LKG required one conflict resolution in `tools/provider_secret_provision.py`: retain the existing LKG provider behavior and add create-only CAS=0 for group read/write secrets; remove unrelated Constant Contact code from the patch.
- Exact on-profile declaration: `aot-group-admin-exact-pilot-v1`, `client-aot-internal`, tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`.
- Separate previously approved read and write Microsoft Graph service identities; no broad directory role writes.

## Verified
- Source-focused Graph connector, credential bootstrap, provider secret, group catalog and release contract test suite: 116 PASS, exit 0.
- Group activation composition tests: 4 PASS, exit 0.
- Original source implementations `group_executor.py`, `microsoft_group_admin.py`, `microsoft_group_admin_activation.py`, `microsoft_group_admin_catalog.py`, `microsoft_group_admin_identity_bootstrap.py` byte-identical to source on merged main as inspected November 19.
- Previously authorized four-file OpenBao AppRole mode correction verified by operator, `READONLY_APPROLE_FILES=4; NO_CONTAINER_REPLACED=true`; root:root 0600 audit receipt exists.
- Root-owned protected production-control readback reports breaker closed, drift pass and no problems. One pre-existing independent advisory for failed documentation reconciliation service is outside this release scope.

## Preproduction and deployment requirements
1. Do not deploy from latest main. Review this exact backport diff from protected LKG and run native GitHub CI/security tests for candidate SHA.
2. Build immutable, separately tagged runtime and MCP candidate images in staging, verify no unreviewed source files, inspect image revision and dependency health.
3. Run native preprod with AOT provider boundary, mocked/no-write Graph tests, exact low-risk pilot acceptance, and protected ticket continuity canary. No Graph POST until separately approved.
4. Release Manager must verify protected breaker/drift, current freeze, credential receipt, four-file root:1000 0640 metadata, current LKG and rollback images, exact scope SHA256, and exact owner approval before unfreezing/promoting.
5. Any runtime or MCP replacement requires explicit production-release authorization and verified rollback. Maintain separate protected PMv4 ticket-core/Shadow Gateway containers and preserve ticket throughput.
6. Post-release verify both group capabilities appear only for the authorized AOT owner; obtain exact-action approvals for group create and subsequent member-add, and independently read back both. Never blindly retry Graph POSTs.

## Rollback and bounds
Rollback target is the actual current protected runtime source and retained matching images at LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. A rollback must disable the group profile and omit only four new group AppRole bind mounts, restore original freeze/holds, and verify ticket-core, MCP, central authorization, and no group capability visibility. No unrelated service is to be touched. A code-only candidate, successful tests or an audit receipt is not production-release eligibility by itself.

**Status**: Candidate source engineering. NOT approved for production, NOT deployed, no Entra Graph writes performed.
