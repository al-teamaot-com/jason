# PMv4 A1 — integrated replacement candidate, after original exact-owner rollback

**Status:** Review-only integrated source, NOT a signed release, NOT a
production merge, NOT a running gateway.

## Authoritative on-host recovery

The first Owner-approved A1 release
`owner-mcp-319c697027a146beac98818e5305a971`
failed while the disconnected gateway exhausted the small 512 MiB,
64-PID and half-core resource budget. The native rollback pointer returned
to the 40-zero baseline but the Compose project was left running, so the
original root journal remained pending. We verified ownership by the exact
A1 Docker image, project/service/source labels, and removed only this failed
Compose project without removing its state volume.

The Owner then ran the source-reviewed **original Owner-authorized
rollback** via `pmv4_a1_recover_existing_owner_local.sh --recover`.
Root postflight reported both native receipt and original root audit
reconciled, and NO NEW OWNER AUTHENTICATION. Independent subsequent live
readback confirmed the Docker project had no containers, original empty
shadow release pointer, no staged approved/reviewed manifests, no shadow
gateway token, no candidate release tree, original production runtime
healthy, MCP running, drift PASS zero problems, and original freeze/hold.

The original A1 signed proof and its 8c2064-specific root release journal
remain immutable historical evidence. NEVER reuse that approval to promote a
new container or overwrite the original journal.

## Consolidated replacement source

This branch integrates:
- Original A1 exact one-Owner source fixes from PR #2496 (Docker 29
  lowercase **absent-object** result scoped strictly to the isolated
  shadow identity).
- The bounded source-only preproduction resource/profile and error
  attribution corrections from PR #2502. Resource changes are exclusively
  `pids_limit 64 -> 256`, `mem_limit 512m -> 2g`,
  `cpus 0.5 -> 1.0`, probe timeout `8s -> 15s`, startup
  `60s -> 120s`. No provider credential or production-host privilege
  added. Network none, ports [], UID/GID 1000, read-only root,
  dropped capabilities, no-new-privileges, restart:no all unchanged.
- Corrected host transaction reporting: a genuine native release-lock
  acquisition OSError remains a host transaction denial, while an error
  from inside the safeguarded release/rollback body retains its actual
  exception so the root rollback decision can be audited accurately.

This combined branch is reviewed against protected main commit
`8c2064193d74cc41b52369681febbc0a74fa96f7`. Source-only tests exercise
original signed packet semantics, exact native release safety, Docker 29
absence, isolated image/profile, host transaction lock behavior, resource
and rollback regression, without starting any container. Source and CI
checks **do not prove actual OpenClaw gateway health**.

## Remaining release gates before asking Owner again

1. This consolidated branch must finish all CI/security review and be
   reconciled with the governing protected-source/production freeze policy.
2. A NEW immutable preproduction candidate packet must be generated from
   the exact source SHA ultimately accepted into protected main. The
   original packet and Owner proof are consumed; using their SHA/policy
   for a new image/profile is forbidden.
3. A NEW exact root executor and root journal version must be pin-verified
   so the previous attempted A1 source/audit files are never overwritten,
   and its rollback to the still-empty baseline is independently tested.
4. The independent root-only active watchdog allowlist and both release
   lock inodes must be checked before any Owner challenge. Earlier root
   policy admission remains exactly one optional shadow-container name,
   NOT a requirement to keep the shadow running.
5. Actual isolated gateway startup health, memory/PID headroom, native
   receipt rollback, and independent preexisting Ticket Core continuity
   must be proven before stage A1 can be called operational. A positive
   source-level dry run alone cannot certify live health.
6. Only after all accessible CI, nonprivileged and privileged checks PASS
   should a **single** authenticated exact-action Owner decision be
   requested for the replacement install/activation. There is no Teams
   approval requirement, no standing approval, and no production freeze
   override.
7. C isolated worker cutover, D runbook registry lifecycle, and E PMv3
   retirement remain separate release gates. Source-only passing PRs do
   not constitute deployed production readiness.

**No Owner action needed merely to review this consolidated source.**


## Concurrent engineering source reconciliation

**Integration coordination: #2496 #2502.** This combined change is directly
based on the exact #2496 reviewed head and includes both original #2502
commits by normal cherry-pick. The overlapping Docker 29 adapter,
A1 local Owner launcher, isolated shadow Dockerfile, host lock adapter and
Compose resource profile have been inspected as one source tree and their
combined A1 tests rerun. PR #2503 is therefore the single *source review*
candidate for this iteration, not authority to merge or activate any
runtime. Do not independently merge #2496 and #2502 into a different
protected-main ordering without a fresh conflict and hash review.
