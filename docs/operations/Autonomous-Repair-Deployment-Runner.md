# Autonomous Repair Deployment Runner

**Status:** Source implemented; production activation pending acceptance  
**Owner:** Jason Architecture Authority  
**Authority:** J-CHANGE-001; J-CHANGE-002; Jason Deployment System  
**Scope:** Rootless host execution of pre-authorized Jason software repair releases  
**Canonical source:** Yes  
**Last reviewed:** 2026-09-28

## Purpose

The Autonomous Repair Deployment Runner completes the J-CHANGE-002 repair lane without exposing the Docker socket, host shell, or root privileges to Jason Runtime.

The flow is:

```text
merged SUPPORT repair PR
        |
        v
runtime repair maintenance
        |
        v
JKD-001 jason-autonomy-worker EXECUTE grant
        |
        v
deployment.repair.apply
        |
        v
/var/lib/jason/openclaw/autonomous-repair/requests
        |
        v
rootless host runner (user al, docker group)
        |
        +-- independent J-CHANGE-002 reclassification
        +-- exact live rollback revision check
        +-- repair merge first-parent check
        +-- exact candidate worktree/build
        +-- existing production-deploy.sh
        +-- live revision + health verification
        +-- rollback on failed verification
        |
        v
durable result evidence
```

## Authority boundary

The runtime capability `deployment.repair.apply` does not deploy anything directly. It may only write one bounded, fingerprinted request into the existing host-backed `/var/lib/jason/openclaw` state boundary.

The apply capability is restricted to the exact service identity:

`jason-autonomy-worker`

Activation creates only these JKD-001 grants:

- `deployment.repair.apply` — EXECUTE, approval not required under J-CHANGE-002;
- `deployment.repair.status` — OBSERVE.

No wildcard, technician, provider, Docker, shell, or administrator authority is granted.

The action is intentionally not exposed as a general MCP conversational write action.

## Host privilege boundary

The host runner executes as the existing `al` account.

The production host already grants that account membership in the `docker` group. The runner does not require `sudo` or root.

Jason Runtime does not receive:

- `/var/run/docker.sock`;
- host shell execution;
- systemd control;
- unrestricted filesystem access.

## Activation profile

The runtime capability is disabled unless:

`JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE=autonomous-repair-v1`

Unknown profile values fail runtime composition.

Source presence alone does not activate repair deployment.

## Candidate discovery

The runtime maintenance worker checks bounded GitHub metadata at a configured interval.

It considers only merged PRs targeting `main` whose PR metadata explicitly says:

`Release class: autonomous-repair-candidate`

The worker also requires the repair merge's first parent to equal the exact live runtime source revision before it queues anything.

This prevents a repair release from accidentally promoting unrelated changes that merged into `main` while production remained behind.

## Durable request contract

Each queued request contains:

- exact candidate merge SHA;
- exact live rollback SHA;
- SUPPORT item;
- merged PR number;
- post-deploy verification declaration;
- autonomous workload identity;
- organization;
- orchestration execution/correlation identifiers;
- SHA-256 request fingerprint.

Idempotency is bound to immutable repair/authority material rather than transient execution identifiers. Repeated maintenance passes therefore do not create duplicate repair requests.

Request and result files are mode 0600 beneath directories mode 0700.

## Independent host verification

The host runner never trusts the runtime classification alone.

Immediately before any build, it verifies:

1. live `jason-runtime` is healthy;
2. live `com.teamaot.jason.source_revision` is an exact SHA;
3. requested rollback SHA equals that live revision;
4. candidate commit exists and is reachable from current `origin/main`;
5. candidate equals the merged PR commit;
6. the merge commit has a production-side parent equal to live production;
7. J-CHANGE-002 classification independently passes using current PR files and check runs;
8. human approval is not required;
9. the SUPPORT item in the PR matches the request;
10. autonomous production execution is enabled by policy.

Any uncertainty fails closed before Docker build/deployment.

## Deployment

The runner creates a detached worktree for the exact candidate SHA and builds a candidate runtime image from that worktree.

It then invokes the existing canonical:

`infrastructure/jason-runtime/production-deploy.sh`

with the exact candidate image and SHA.

That script continues to own live-container replacement, image alias promotion, health checking, and immediate replacement rollback behavior.

## Verification and rollback

Success requires:

- live container health = `healthy`;
- live `com.teamaot.jason.source_revision` = exact candidate SHA.

If a failure occurs after replacement, the runner invokes the same deterministic production deployment path with `jason-runtime:rollback-current` and the exact recorded rollback SHA.

Rollback is accepted only when the live source label returns to the rollback SHA and runtime health is healthy.

If rollback cannot be verified, the runner records a hard failure and requires human review.

## User systemd units

The source includes:

- `jason-autonomous-repair-runner.path`;
- `jason-autonomous-repair-runner.service`.

The path unit watches the request directory and invokes a single-flight oneshot service.

The service uses the stable installed runner at:

`/home/al/.local/lib/jason/autonomous_repair_host_runner.py`

It does not execute a mutable feature-branch script.

## Installation

After source is merged to protected `main`, run the rootless installer from that exact merged checkout:

```bash
python3 tools/install_autonomous_repair_host_runner.py --activate
```

The installer:

- copies the runner into the stable user-local path;
- installs user-level systemd units;
- creates the bounded spool directories;
- reloads user systemd;
- enables the path watcher.

## Activation sequence

Production activation requires this order:

1. merge source through protected `main`;
2. install rootless host runner;
3. verify path unit active;
4. run non-mutating invalid/preflight request acceptance;
5. build exact merged runtime candidate;
6. deploy it through the normal human-approved release path with the activation profile set;
7. verify capability/authority registration and runtime health;
8. independently verify the host runner still has no root requirement;
9. only then enable `automatic_production_execution_enabled=true` in the repair policy;
10. verify the Development & Release Control Board reports autonomous execution enabled.

The final policy flip is a release-governance change and must itself use the normal protected change path.

## Failure behavior

A failed/rejected request produces bounded durable result evidence and does not retry by inventing a second repair.

The development/support workflow remains open for investigation.

No failed autonomous repair may:

- change its candidate SHA;
- change its rollback SHA;
- widen its file scope;
- bypass protected checks;
- fall back to arbitrary shell execution;
- silently convert to a normal release.

## Initial scope

Version 1 supports only the production `jason-runtime` container.

Teams gateway, MCP, OpenClaw bridge, observability services, provider systems, and client endpoints remain outside the autonomous repair deployment scope until separately designed and approved.
