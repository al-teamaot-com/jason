# Unified licensed-Owner + audit issuer candidate — one scoped MCP image

**State:** Source-only. **No production deployment, Owner proof, or Root transaction is performed.**

## Purpose and exact ancestry
Avoid two separately disruptive MCP release transactions when preparing Jason's already-reviewed licensed Owner correction and the one-use daily audit journal adoption issuer. Both source components are independently narrow descendants of the original production LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`:
- Owner policy candidate: `ec891ae49428357ccae8fa3b990c021a124b41d9`, approved only for source engineering.
- Audit issuer candidate: `1bb2fe561b1189b3c46363a84ecf3eaaa39f5877`, approved only for source engineering.

This candidate starts from the exact Owner correction and adds only the four reviewed audit-issuer files from the second change. Git applied its MCP server addition without conflicts; the source has one additive audit tool, not a second server or authorization engine. It does not integrate the unrelated full current Main runtime into the protected LKG.

## Scope and deny boundaries
- Owner profile `jason-owner-v1` must independently verify licensed human Entra tenant+OID through existing signed OAuth middleware. The unlicensed Entra administrator identity is NOT the Jason Owner. No forged chat identity, email-only allowlist or user impersonation can authorize anything.
- Jason's service identity remains responsible for all provider actions. This change grants no broader service write, host Root, automatic provider remediation or standing release privileges.
- `approve_audit_journal_adoption` signs exactly one Root-staged, 600-second, hash-pinned `ADOPT-EXACT-DAILY-AUDIT-JOURNAL` offer with its original licensed Owner bearer. The affirmative exact phrase, installed service signing key, scope+manifest+freeze and current Root offer must all match. No device code, terminal prompt, archive write or Root command is part of the tool.
- `JASON_AOT_ADMIN_APPROVER_PROFILE=jason-owner-v1` is the opt-in administrative Owner profile. `JASON_AUDIT_JOURNAL_OWNER_ISSUER_ENABLED=true` is separately governed and fail-closed absent a Root offer. Merely building or running this image without these verified activations conveys no authority.
- The production freeze, circuit breaker, Root desired-state policy, original runtime, independent Ticket Core, JSON registry and all provider identities are preserved. No direct `docker run` replacement under freeze.

## Exact image/release boundary
The original production MCP rollback image is `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`. Original runtime remains `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`. The candidate Dockerfile copies precisely the amended MCP server and one additional audit issuer Python file into the immutable original MCP base; normal UID1000, existing mounts and all previously registered tools remain. Candidate image ID and exact source commit must be recorded from an isolated no-network build, never guessed.

Prior to production: require reviewed protected Main ancestry of exact candidate, up-to-date CI, original image/rollback and freeze digests, a separately installed native Owner-signable release profile, exact Owner decision and Root production breaker/peer/transaction revalidation. A native release must replace only `jason-mcp-pilot`, protect its original image/configuration, verify all 37 existing tools plus exactly one new tool, confirm the licensed Owner is accepted and the unlicensed admin is rejected, and roll back on any failure. Owner's earlier archive approval is NOT a signed new software release.

After the issuer is genuinely active, Root must refresh the installed audit-worker exact Main/SHA policy and declare any systemd unit in protected desired state **before enabling it** (the earlier undeclared watcher correctly caused drift). Then and only then stage the one-use archive offer, have the authenticated Owner sign within 10 minutes, and adopt with independent Root checks, complete event/restore parity, daily rollover, native health and actual root-space reclaim. Do not stage an offer prematurely: it is single-use and expires.

## Evidence and deferred acceptance
Focused source tests include the licensed Owner policy, admin-account denial, signed audit-issuer acceptance/negative/replay cases and existing deploy-contract gates. A no-network isolated image must prove unchanged baseline tool names and new tool registration; a future production promotion must independently prove live Owner claims, healthy runtime and original freeze/breaker. CI and a source commit do not by themselves authorize deployment or claim whole-objective completion.
