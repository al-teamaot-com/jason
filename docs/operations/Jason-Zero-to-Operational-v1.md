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

## Host acceptance plan preflight

The host acceptance runner now has a read-only preflight bundle.

Before a blank host is mutated, the plan must prove:

- an authorized Candidate Host Identity;
- a genuinely clean supported host;
- immutable current and next release archives with exact SHA-256 and source SHA;
- safe release archive members;
- valid MSP configuration and MSP policy;
- a secret-presence attestation containing every enabled-provider logical secret reference;
- an X25519 recovery recipient public key;
- a privately stored Ed25519 recovery signer private key;
- provider canary coverage exactly matching enabled providers;
- a declared governed read workflow for acceptance;
- the second-clean-environment requirement;
- production_authorized=false.

The host-preflight CLI performs no deployment mutation.

## Candidate runtime startup

Host-mode acceptance does not reuse Production deployment scripts.

The candidate runtime starter:

- requires an authorized Candidate Host Identity;
- requires the candidate Deployment Manifest instance to match that identity;
- requires complete logical secret-reference attestation;
- requires a protected runtime environment file;
- generates a candidate-only Compose overlay;
- uses a candidate image tag and candidate container name;
- sets restart=no for the acceptance runtime;
- ensures declared external networks exist;
- runs docker compose config --quiet before startup;
- starts only the candidate runtime service;
- waits for /healthz;
- requires runtime health to return the exact expected Deployment Manifest identity.

A runtime process that is merely running, or healthy under the wrong deployment identity, does not satisfy the start phase.

## Candidate service stack for host acceptance

Host-mode acceptance now has explicit candidate-only service contracts rather than reusing Production deployment commands.

Candidate Runtime:
- uses a release-derived candidate image;
- runs under a distinct Compose project and container name;
- publishes health only on 127.0.0.1:18080;
- requires the runtime health response to carry the exact candidate Deployment Manifest identity;
- overrides the Production volume list with canonical candidate state plus only the explicitly declared protected credential files.

Candidate dependencies:
- create only the declared candidate Docker networks;
- run OpenBao with configuration from the immutable release but Raft/audit/log state under /var/lib/jason/openbao;
- run Ollama with reconstructable cache state under /var/lib/jason/cache/ollama;
- block readiness while OpenBao is uninitialized or sealed;
- block readiness until the selected Ollama model is present.

Candidate MCP:
- builds reproducibly from the exact candidate Runtime image rather than the historical local generic-governed image;
- runs as a distinct candidate container;
- publishes only on 127.0.0.1:18000;
- never invokes the Production MCP deployment script;
- reuses candidate state and protected credential mounts;
- executes the MCP governance postcheck before acceptance continues;
- runs and persists the existing provider health canaries.

Provider canary authority is candidate-only, observe-only, time-bounded, and restricted to the exact organization and provider set declared by the host acceptance plan. The prior AOT organization hard-code is removed from this canary path.

These components are source/test complete but have not been started on the current Jason host.

## Candidate dependency preparation

Host-mode acceptance now has an explicit dependency phase rather than assuming services already exist.

The candidate dependency controller:

- requires Candidate Host Identity authorization;
- creates only the declared Jason networks;
- starts candidate OpenBao and Ollama with restart disabled;
- stores OpenBao durable state under var/lib/jason rather than inside the immutable release;
- stores Ollama cache under var/lib/jason/cache;
- verifies OpenBao is initialized and unsealed before dependent services are considered ready;
- verifies the configured Ollama model is present, with an optional explicit model-pull step.

A running but sealed or uninitialized OpenBao blocks the acceptance chain.

## Candidate runtime environment contract

The candidate runtime environment is a protected path/reference file, not a secret-value file.

The runtime environment parser:

- rejects duplicate or malformed keys;
- rejects direct password, token, private-key, or secret values;
- permits only declared file/path references for secret-bearing material;
- requires the configured Ollama model and SES sender;
- validates every protected mount source before Docker startup.

For the current v1 acceptance profile, secret mounts are minimized to the exact Autotask and Datto RMM read AppRole RoleID/SecretID files. Unrelated SES, OpenAI, Graph, IT Glue, and EDR credentials are not prerequisites for the clean-host acceptance path.

Candidate runtime binds health only to the configured loopback candidate port and persists authority/openclaw state outside the immutable release.

## Candidate MCP startup

Candidate MCP is built reproducibly from the already-built candidate runtime image by supplying that exact image as the MCP Dockerfile BASE_IMAGE.

It does not depend on the historical local generic-governed MCP image.

The candidate MCP controller:

- uses a candidate-only image and container name;
- binds MCP health/resource access only to the configured loopback candidate port;
- runs with read-only root filesystem and restart disabled;
- mounts candidate authority/openclaw state from the candidate root;
- mounts protected credential path references read-only;
- validates runtime/MCP environment compatibility before build;
- performs a post-start governance check requiring central-orchestrator execution, the generic governed execution tool, and direct provider access disabled;
- never invokes production-deploy.sh or the live-container promotion helper.

Provider canary results are persisted as non-secret candidate evidence.

## Candidate provider-canary authority

Provider health acceptance no longer assumes organization aot or probes all providers unconditionally.

The acceptance plan supplies:

- exact organization ID;
- exact enabled provider subset.

A candidate-only canary principal receives time-bounded OBSERVE grants only for the selected synthetic canary capabilities. The grants carry no client wildcard, require no mutation permission, and expire after the bounded acceptance window.

The canary runner uses that explicit organization and provider set. Wrong organization, unsupported providers, conflicting identity, or excessive grant lifetime fail closed.
