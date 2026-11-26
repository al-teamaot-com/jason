# PMv4 A1 v4 — exact immutable shadow candidate preparation

**Status:** SOURCE-ONLY. Building and testing this source does not stage root files, sign a release, deploy Docker, alter Ticket Core, or change the production freeze or promotion hold. Privileged root preflight and one new authenticated exact Owner approval remain mandatory before any future activation.

## Reason

The original v3 exact A1 release (`c999216a3df9d2422833b90403c31530c323f467`) was cryptographically approved, rejected by the Docker29 named-volume readback mismatch, and then fully reconciled under its original Owner consent. The v3 release and approval cannot be replayed. PR #2507 corrected the Docker29 exact named-volume security readback; PR #2508 provided the original-approval native rollback. The current production runtime remains on `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.

## New release contracts

The v4 immutable builder generates a distinct `pmv4-a1-one-owner-exact-disconnected-shadow-bootstrap-v4` action and confirmation, exact source SHA + local pinned image SHA, generated root-owned-code hashes, preapproval source/CI verification, single-use Owner authorization, and an isolated shadow-only scope. Build inputs come from Git object blobs at a CI-verified protected-main SHA; builder itself cannot install, start or approve anything.

Root acceptance requires all historical approvals and no pending receipt. Exactly two native receipts are permitted, each matching a fixed previous SHA, exact approval ID, `state=rolled_back`, and zero empty-baseline rollback. Independently, the protected v2 root audit must be terminal rolled_back and its already-consumed approval root absent. The protected v3 root audit must have a valid SHA256 link chain, original source/approval identity, no committed event, and exact terminal `reconciled_original_exact_owner_rollback`; its original signed Owner proof, native `reconciled=true` receipt and now-absent staged root files must agree. Any new or unknown receipt, pending native state, tampered audit, foreign container, drift, stale Ticket Core or host lease failure denies before a new Owner request.

The new candidate retains `network_mode:none`, zero published ports, non-root UID/GID, read-only root, no-new-privileges, all capabilities dropped, exact named state volume and private tmpfs, no provider secrets, and bounded image resources. Docker 29's named-volume `HostConfig.Binds` must be the one exact reviewed bind, with a corresponding named `Mounts` item. No host path bind or extra mount is approved.

## Release route

1. Merge only reviewed source to protected `main` after targeted tests and all required CI checks pass.
2. Build an offline local preproduction image with `com.aot.jason.source_revision` pinned to the *exact* merged main source SHA; verify the image ID and reviewed image metadata. Do not start it.
3. Generate an immutable SHA-bound candidate packet and one-shot v4 root/Owner launcher with the existing reviewed immutable-packet builders. No previously consumed Owner proof may be inherited.
4. Run local source preflight, independent root preapproval and zero-mutation health gates. Report exact new source SHA, image SHA, release scope SHA and rollback zero SHA. An authenticated Owner's *new* explicit authorization is then required for the separately governed shadow activation.
5. Only afterward accept A1 as deployed when the root-signed audit shows committed, the native shadow release is accepted, its gateway is healthy, the effective Docker security profile matches exact scope, and the existing Ticket Core remains healthy under unchanged production freeze/hold.

## Evidence and rollback

Source tests include actual Docker29 named-volume and negative host-bind checks, disposable root-generation compilation, exactly two prior receipt admission, pending/extra receipt denial, historical v3 hash-chain tamper rejection, nonterminal audit denial, and rolled-back receipt proof. Candidate-only generation never authorizes production. The rollback pointer remains the original zero SHA (`0000000000000000000000000000000000000000`) for this isolated shadow; preexisting production Core revision is protected separately.
