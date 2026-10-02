# Jason Zero-to-Operational v1 Acceptance

Issue #753 is the final deployability acceptance path.

The acceptance runner is an ordered fail-closed phase machine:

1. install;
2. initialize durable state;
3. start candidate;
4. verify Deployment Manifest identity;
5. verify READY;
6. verify configuration;
7. verify governance;
8. verify provider/client isolation;
9. verify provider connectivity;
10. exercise a governed workflow with durable audit evidence;
11. upgrade;
12. verify upgraded identity/health;
13. roll back;
14. create a Full Recovery Export;
15. destroy/recreate/restore;
16. verify restored READY/equivalence;
17. repeat on another clean environment.

A failure skips all later phases and produces a deterministic receipt.

## Evidence safety

Acceptance receipts contain hashes and non-secret summaries only. Evidence containing secret-bearing keys such as password, root token, unseal key, private key, or access token is rejected and the phase fails.

The acceptance runner can never set or infer Production authorization.

## Synthetic precursor

The current jason_zero_to_operational synthetic runner exercises the full chain on isolated filesystem roots using synthetic system/provider evidence.

It calls real deployability implementations for:

- immutable candidate bootstrap;
- durable state initialization;
- Deployment Manifest generation/validation;
- candidate READY evaluation;
- client-boundary conflict enforcement;
- durable orchestration-event readback;
- encrypted pre-upgrade recovery checkpoints;
- candidate upgrade and rollback;
- Full Recovery Export;
- machine-bound re-enrollment acknowledgement;
- restore to a new root;
- restored durable client-boundary readback;
- second clean-environment reproducibility.

This synthetic mode intentionally sets deployability_proven=false.

Only a complete mode=host run on a genuinely blank supported Ubuntu host may set deployability_proven=true.

Even a successful host-mode receipt must always keep production_authorized=false. Production promotion remains separately governed by the Production Promotion Authorization Standard.

## Host-mode bootstrap authorization

The bootstrap path can target the actual filesystem root only when an explicit Candidate Host Identity is supplied.

Candidate Host Identity requires schema version 1.0, environment=candidate, a non-empty instance ID, and bootstrap_authorized=true. A production identity cannot authorize candidate bootstrap.

Before a blank-host install, the read-only candidate host preflight requires an authorized Candidate Host Identity with safe permissions, root privileges, supported Ubuntu 24.04 x86-64, Python 3.12 or newer, Docker and Docker Compose, and no prior Jason deployment markers or installed Jason units.

The same authorization object is threaded through canonical layout creation, immutable release staging, durable state initialization, portable systemd staging, secret-requirement staging, and Deployment Manifest generation.

Without that identity, all existing live-root guards remain fail-closed.
