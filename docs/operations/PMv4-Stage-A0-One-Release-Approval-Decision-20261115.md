# PMv4 Stage A0 — one bounded Owner release authorization (Owner governance decision)

**Decision date:** 2026-11-15. **Owner:** AOT. **Authoritative issue:** [#2481](https://github.com/al-teamaot-com/jason/issues/2481). **Status:** Approved project-specific *approval-policy amendment*, engineering authorized; production release not authorized.

The Owner responded **"Yes"** to the precise proposal: change issue #2481 so the three specified Stage A0 operations *may execute as one independently verified, atomic release under one authenticated Entra Owner approval*. This displaces **only** the issue's previous requirement for separate Owner approvals for every transition of this exact Stage A0 recovery. It does NOT represent an authenticated signed Entra production approval, a production-freeze exception, or permission to bypass separately governed root activation. One real Entra Owner consent for the complete final immutable candidate remains required.

## Narrowly permitted release transaction

Exact non-runtime source identity: `7b42ce983896711525de4c7955bf9fc43ac003d0`; existing production LKG/rollback `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. Strict ordered A0 operations only:

| Step | Governed action | Exact reviewed scope SHA256 | Exact artifact SHA256 | Action rollback |
| --- | --- | --- | --- | --- |
| 0 | Root-only exact closure helper, policy and empty audit ledger bootstrap | `e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb` | `25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564` | remove exact newly created trusted objects |
| 1 | Add only the missing immutable root source `tools/pmv4_host_install_contract.py` | `089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381` | `ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db` | remove precisely that new trusted inode |
| 2 | Create-only native Stage A0 isolated host objects | `6786baad0fc9d07aca6ba80dedad5c25bcfa7fb3e50fdde7c4d36ad067285eac` | `addba768d1ab92d9507d466fdd3980b93ea2041f42901f5d6e5a2cde81dcb025` | independent root-verified empty baseline |

**Full-machine controls which must remain byte-for-byte unchanged:** production freeze `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`; auto-promotion hold `11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0`; existing production runtime and MCP images; active release pointer; provider data; ticket processing.

## Conditions of this exception

1. One fresh independently verified Entra Owner identity and affirmative decision over the exact **entire** immutable plan. Parent and each derived step cryptographically bind exact scope/source, per-step rollback, expiry, and pinned Owner public key. Signing a parent does not imply an executable root grant; root must independently authenticate original signed evidence, active revocation status, native root approval journal and previous step receipts before every stage.
2. The **single trusted root release transaction** holds native governance/exclusivity through all stages, records intent before each mutation and completes only after all three postflights pass. No partially successful stage is reported as completion. Failures require bounded recovery/conditional reverse rollback of only independently verified newly created objects, never foreign objects or unverified root state.
3. Before any protected write: source-only PR/CI + security/architecture review, exact immutable candidate and source artifact hashes, original production health and breaker, root-only empty targets, native lock, freeze/hold unchanged, root pinned trust code, current approval and revocation, durable one-use journal and rollback. The stage-1-only launcher does not qualify as the complete combined release.
4. Afterward: reverify A0 behavior plus unrelated Ticket Core/MCP services, protected runtime/source, existing production freeze/hold/rollback; retain logs and exact decision/steps/rollback receipts. Automatically keep global freeze and promotion hold in effect.
5. This is a **one-time project-specific exception** to redundant human checkpoints for **this exact complete Stage A0 objective only**. No standing or broader production authority, no merging in unrelated 79-file main changes, and no extension to PMv4 B/C/D stages, provider writes, or other production releases. Those still require independently governed exact release authorization.

## Source acceptance vs live authorization

Current PR #2489 contains sandbox-only schema-v2 grant, journal, attestation and native admission; its production adapter explicitly rejects `production=True` until a separately reviewed, hash-pinned root worker is actually installed. PR #2491 source-only supports the initial root bootstrap but does NOT execute the subsequent source/Stage A0 actions. The previous two-prompt launcher MUST NOT be represented as the approved atomic release mechanism.

The Owner's **"Yes"** changes the *approval aggregation policy*, **not** the authority or method by which untrusted ChatGPT/UID1000 code becomes privileged on the Jason host. The one final Entra Owner consent is reserved until the exact full transaction passes genuine disposable root-mode atomicity, interruption/recovery, safety, and CI evidence. These requirements apply even after one-approval source tests pass.

References: Governance Handbook Part IV (exact release, independent production approval, freeze, root safety, rollback); Part V (no unnecessary human checkpoints); issue #2481's explicit current amended acceptance, PRs #2489 and #2491.

## 2026-11-16 — current-main exact-source staging amendment (preproduction only)

This section updates the technical release SHA and immutable A0 manifest for the *already approved one-Owner-decision policy*, without representing a new production authorization. The historical 2026-11-15 table above remains an accurate record of the earlier 7b42 candidate; it is **not** executable authority for the current source.

A separately authorized November 16 two-file root-trust migration replaced the pinned sparse-stage policy with a verified current-main policy for source SHA `8c2064193d74cc41b52369681febbc0a74fa96f7`, sparse scope SHA256 `00bbf9884a1f724886be50d100a6aec2f3dfece6ec18177ca39d18768c6248e1`, and immutable thirteen-file archive SHA256 `1e30acee8e9a5d5fe8478be644c51a71cabb2651875961540eae4f10d2903998`. The **old one-use staging audit ledger** was already consumed for candidate 7b42 on November 14 and must never be cleared, overwritten or replayed. On November 16, the source directory for 8c20 was absent, so separate re-execution of that consumed staging action correctly failed closed.

The reviewed replacement A0 transaction keeps **three ordered audited actions and one Entra-authenticated exact Owner decision**, but expands action zero to include the prerequisite thirteen-file source stage under the **same original root transaction lock**. These are the current reviewed source-only terms:

| Step | Exact current-main A0 action | Scope SHA256 | Artifact SHA256 | Reverse rollback |
| --- | --- | --- | --- | --- |
| 0 | Exact current-main 13-file sparse source stage plus original two-root-file closure-helper bootstrap, one Owner signature and lock | `0f4a5cb3774c804a898cc3d987ee9d48c5fc6bb2cee9ab000d5dcabf09d94eff` | `041a3a94fd6287a749e7ca981ff73fc2e1fd8e1189b710ef859279e871a776c9` | Verify each newly created root-owned inode, remove only these trusted objects, return new 8c20 source to original absence |
| 1 | Add only the missing immutable `tools/pmv4_host_install_contract.py` source blob | `4f36e1eee0d5051484aeaadc77877525274faf880c9638b8e5ffe56eddc78a42` | `ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db` | Verify and remove only the one new inode |
| 2 | Create and verify the exact native A0 isolated host objects | `509e2a39d323009a55af2e5244214fae3e8e14c910a5c4ece4b3da73a0fa0ae3` | `bd18226b5f82e276e2f7cc1229c7d0046c99401c4bf4a0753de7ec2b13f237f0` | Reverse verified native objects to the previously empty baseline |

The revised source-only review contract SHA256 is `2682ef9c5f0a31ede23b8a222bac596d3516a188b54b9ebb78533ee2f684a1c0`. Source staging and every subsequent action must be cryptographically bound to the complete release manifest; root preflight and CI must pass before fresh Owner authentication. The original one-shot audit ledger remains unchanged. The production LKG pointer, runtime and MCP images, Ticket Core processing, freeze, promotion hold and all provider data remain unchanged. Neither this documentation amendment nor CI success authorizes a production write. Final status requires native privileged postflight and durable root audit evidence.
