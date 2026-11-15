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
