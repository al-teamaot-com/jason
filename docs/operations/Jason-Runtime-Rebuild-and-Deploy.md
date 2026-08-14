# Jason Runtime Rebuild and Deploy

**Status:** Active operations runbook  
**Updated:** 2026-08-14

## Authoritative deployment topology

Do not guess the Compose location or deployment inputs.

Known running-service facts have historically included:

- Container: `jason-runtime`
- Image tag: `jason-runtime:local`
- Compose project: `jason-runtime`
- Compose service: `jason-runtime`
- Compose working directory: `/home/al/projects/jason/infrastructure/jason-runtime`
- Compose file: `/home/al/projects/jason/infrastructure/jason-runtime/compose.yaml`

These are examples of previously verified state, not perpetual authority.

Before every rebuild, derive the current Compose working directory, Compose config file(s), and service name from the running container's Docker Compose labels. Do not rely on this narrative record when fresh container evidence is available.

## Required Compose inputs

The deployment requires values including:

- `JASON_OLLAMA_MODEL`
- `JASON_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_OPENBAO_SECRET_ID_HOST_PATH`
- `JASON_SES_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_SES_OPENBAO_SECRET_ID_HOST_PATH`
- `JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH`

Do not infer these from memory. Derive the current values from the running service environment and bind mounts.

Never print secret contents. Verify only paths/presence/metadata.

## Protected secret bind verification

An ordinary operator account may be unable to `stat` or `test -f` a valid secret source because one of its parent directories intentionally denies traversal. A failed ordinary-account metadata check is therefore not sufficient evidence that a production secret source is missing.

Use this order:

1. Derive each source path from the running container's bind mount for the required secret destination.
2. Confirm the running container currently sees the destination as a regular file where applicable.
3. If the host path is directly visible to the operator, a metadata-only host existence check is acceptable.
4. If host traversal is intentionally restricted, use a Docker daemon bind probe instead of weakening directory permissions or reading the secret.

A Docker bind probe should:

- start an ephemeral container from an already available trusted local runtime image;
- mount the candidate host source read-only to a neutral probe path;
- test only whether the mounted target is a regular file; and
- discard the container immediately.

Example pattern:

```bash
docker run \
  --rm \
  --user 0:0 \
  --entrypoint python \
  --mount "type=bind,src=$SOURCE,dst=/probe,readonly" \
  jason-runtime:local \
  -c 'import os,sys; sys.exit(0 if os.path.isfile("/probe") else 1)'
```

Do not print or hash secret file contents during this check.

This method uses the same Docker privilege boundary that performs the production bind and avoids misclassifying a permission-visibility problem as a missing secret.

## Host validation environment

When running runtime-service/OpenClaw connector tests directly on the Jason host, expose the same implementation source roots used by the runtime image.

Current source-root pattern:

```bash
export PYTHONPATH="$PWD/implementation:$PWD/implementation/cap-007/src:$PWD/implementation/connectors/openclaw/src:$PWD/implementation/runtime_service/src"
```

At minimum, verify imports before treating pytest collection failures as implementation failures:

- `jason_cap_007`
- `jason_openclaw`
- `jason_runtime`
- `kernel`
- `orchestrator`

The production runtime Dockerfile is the implementation source of truth for the source roots it exposes. If packaging changes, derive/update the host validation environment accordingly rather than preserving a stale path list here.

## Safe deployment sequence

1. Record the current branch, HEAD, and `git status --short`.
2. Confirm the working-tree change scope is exactly the intended deployment scope.
3. Run `git diff --check`.
4. Re-run the relevant deterministic tests using the correct host source-root environment.
5. Derive current Compose working directory/config/service from the running container labels.
6. Derive required interpolation inputs from the running container environment and bind mounts.
7. Verify required secret bind sources without reading secret contents; use the Docker bind-probe method when direct host traversal is unavailable.
8. Run Compose configuration validation from the derived authoritative Compose directory/file.
9. Record the currently deployed image ID.
10. Create and verify a rollback image tag pointing to that exact image before building the replacement.
11. Build `jason-runtime:local`.
12. Confirm the build produced the intended image ID. If the work should materially alter the image, investigate an unexpectedly unchanged image before deployment.
13. Only if build succeeds, recreate/start **only** the `jason-runtime` Compose service unless the governed change explicitly requires broader mutation.
14. Poll container/health status with a bounded timeout.
15. Verify the running container image ID matches the newly built image ID.
16. Verify source parity for the changed implementation files between the host worktree and the running container where practical.
17. Verify the health endpoint and expected Central Orchestrator authority.
18. Verify hardening controls that matter to the deployment, including non-root runtime user, read-only root filesystem, non-privileged mode, capability drop, and `no-new-privileges` where configured.
19. Run the bounded live functional proof appropriate to the change.
20. Report each return code and final container state.
21. If any step fails, report the first meaningful error and continue the interactive troubleshooting session; do not terminate the operator's shell/session.

## Rollback requirement

Rollback success is not established merely because a container restarted.

A runtime rollback must:

1. retag/restore the verified pre-change image as the expected deployment image;
2. recreate only the affected service unless broader recovery is required;
3. wait for bounded healthy/running state;
4. verify the running container's image ID matches the recorded pre-change image ID; and
5. where the failure involved artifact/source replacement, verify restored source/artifact parity or another equivalent content check before declaring rollback complete.

If rollback verification fails, report rollback as failed even if the service process is running.

## 2026-08-12 deployment proof

The semantic resource-inquiry changes were validated before deployment. The final build completed successfully, the container restarted successfully, and the runtime health check passed.

The deployed worktree at that historical checkpoint remained intentionally uncommitted at HEAD `25bc07a`; deployment success was therefore correctly distinguished from Git durability.

Historical functional proof through Teams:

`AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm.`

## 2026-08-14 exact-message idempotency deployment proof

The exact authenticated Teams-message idempotency work was validated, built, deployed, live-proven, and then committed durably.

Before deployment:

- all required OpenBao/provider secret bind sources were derived from live mounts;
- ordinary host metadata checks failed on protected paths because of directory traversal permissions;
- Docker daemon read-only bind probes verified all required sources without reading secret contents;
- Compose configuration validation passed; and
- a rollback image tag was verified against the exact pre-change runtime image ID.

Pre-change image:

`sha256:88aeadb5e3838629b0a25e0b646980923cfa080bca715033cceeef8f9f6fb029`

Rollback tag:

`jason-runtime:pre-message-idempotency-20260814T151057Z`

Deployed image:

`sha256:060f0b5fe98611fc9bb634bc2d11d87d239b685fb441a4b6fae35103298e8ac6`

Deployment verification passed for:

- bounded healthy runtime startup;
- deployed image ID parity;
- host/container source parity for changed ingress/runtime/HTTP implementation;
- idempotency implementation presence;
- health endpoint response and Central Orchestrator authority; and
- runtime hardening.

A subsequent live signed proof showed the first governed request completed successfully and a second independently signed envelope representing the same Teams message returned `status=duplicate` / `error_code=duplicate_message` without a second governed execution.

Durable implementation commit:

`aacc1cb7527e640331aa43cbc316c6c22c56ca77`

Durable proof record:

`docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md`
