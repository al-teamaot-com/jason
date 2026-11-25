# Constant Contact OAuth plus JES-005: isolated release ancestry

Engineering evidence only. No deployment approval.

- Owner explicitly approved the protected-ancestor policy in the November 12 Constant Contact continuation; exact-SHA production approval remains separate. JES-005 records the policy in the source registry.
- Source repair #2472 and complete release-control correction #2475 are normally merged into development main. Reconciled prior pinned-release logic from #2156; no competing older Teams/Workboard authority is activated.
- Final immutable candidate: 39b00eb2b53f44eb48839f977a8838a8a127b6bf. Git tree 06ae2a820476837b08e15245dd7185f765b3705b.
- Production/rollback baseline at preparation: d1b8c196dadd4b672ec8ba47075f27bb61c98d63.
- Exact baseline-to-candidate binary diff SHA256: 25132ab3cf1ecf5b2e70b6a582858fbf86ab020e3613115a7b57894025eb0896. Eleven files only: OAuth header/test/incident document (three), approved release-scope/core-classification/tests/CI/standard (eight). No unrelated source activation.
- All 22 exact-snapshot CI workflows PASS. Complete focused suite: 295 tests and 5 subtests PASS. Additional exact-snapshot signed Owner/root/freeze/atomic regressions: 38 PASS. Real provider token exchange remains unverified.
- Draft #2476 MUST NEVER merge directly because its isolated LKG-based tree would remove newer development. Prior snapshot #2473 and its unapproved native candidate are superseded and must not deploy.
- This bridge starts at current protected main, merges the exact final snapshot with git merge -s ours --no-ff, independently verifies byte-for-byte main source/configuration equality, then adds ONLY this document. Never squash away the exact snapshot parent. Protected bridge CI must pass normally.
- Native candidate preparation must use this exact snapshot's own Production Manager controller because controller source changed. Require immutable images, isolated writable-state preproduction, source/native contract and failure/rollback tests, actual full scope receipt, current healthy rollback, under-lock protected-history checks and separate authenticated signed Owner exact-SHA approval.
- Preserve the already approved CC read-only AppRole mounts, shared encrypted OAuth state and Owner signer. Newer candidate-file/control changes or unknown evidence deny pinned release. Automatic candidate selection remains newest-main; freeze, signed authority and mutation controls remain unchanged.
- Only after verified deployment may a fresh real AOT OAuth consent flow complete. Account/list binding, consent-backed import/readback and GET-only scheduler activation remain independent acceptance gates.
