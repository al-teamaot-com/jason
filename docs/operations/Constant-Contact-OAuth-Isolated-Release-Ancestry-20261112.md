# Constant Contact OAuth repair: source-neutral release ancestry

Engineering evidence only; no production approval.

- Production LKG/rollback: d1b8c196dadd4b672ec8ba47075f27bb61c98d63.
- Exact isolated source candidate: 18be575bf29a7e2adf5fac94a26036e5cbb5645b; Git tree eb2adddc4d7699ea566bca03d2c292d3d21ff5bf.
- Production-to-candidate scope: token_exchange.py (one explicit truthful User-Agent header), its two negative-to-positive regression cases, and the incident/release document. No other source/configuration change. Binary diff SHA256 6e6c280967aee960afb4a4ef5d27d4c8939d45498d5c522cad7f5680d6512f38.
- Normal source PR #2472 merged as 97f6017e5c333132706aeadb0e5a8d0441497ddc. It preserves all current-main engineering; it is not a narrow deployment candidate.
- Draft snapshot PR #2473 must NEVER merge directly. Its deliberate older source tree would remove unrelated engineering if directly merged. It exists only to obtain exact-source CI. The failed first integration run required explicit reviewed overlap documentation; a fresh reopened PR event evaluates the corrected scope without changing snapshot bytes or skipping checks.
- This bridge uses the already documented source-neutral release ancestry pattern: start from protected main, git merge -s ours --no-ff the exact snapshot, verify the source tree equals protected main byte-for-byte, then add only this evidence document. No main implementation file is changed. Do not squash the bridge because the exact snapshot must remain an ancestor.
- Both snapshot and bridge required CI must succeed, including independent security and provider regressions, before native release preparation. A source merge grants no production authority. Never substitute current main as this Constant Contact candidate or waive native candidate ancestry/checks.
- Native Release Manager must build the exact isolated snapshot once, verify its full three-file scope, unchanged production baseline/health, preproduction and rollback. Preserve the separately approved two read-only CC AppRole mounts, shared encrypted OAuth storage and existing Owner signer. Fail if those would be lost.
- Require separately authenticated exact-SHA Owner release approval. After verified deployment, initiate a fresh one-time OAuth flow and obtain actual AOT consent. No failed code/state replay, contact import or scheduler activation is authorized by this document.
