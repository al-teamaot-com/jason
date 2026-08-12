# Jason Runtime Rebuild and Deploy

**Status:** Active operations runbook  
**Updated:** 2026-08-12

## Authoritative deployment topology

Do not guess the Compose location or deployment inputs.

Running service facts verified 2026-08-12:

- Container: `jason-runtime`
- Image: `jason-runtime:local`
- Compose project: `jason-runtime`
- Compose service: `jason-runtime`
- Compose working directory: `/home/al/projects/jason/infrastructure/jason-runtime`
- Compose file: `/home/al/projects/jason/infrastructure/jason-runtime/compose.yaml`

When uncertain, derive these from the running container's Docker Compose labels before attempting a rebuild.

## Required Compose inputs

The deployment requires values including:

- `JASON_OLLAMA_MODEL`
- `JASON_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_OPENBAO_SECRET_ID_HOST_PATH`
- `JASON_SES_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_SES_OPENBAO_SECRET_ID_HOST_PATH`
- `JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH`

Do not infer these from memory. Derive the current values from the running service environment and bind mounts. For host paths that an ordinary account cannot stat because of directory permissions, verify presence with appropriate privileged metadata access rather than declaring the path missing.

Never print secret contents. Verify only paths/presence/metadata.

## Safe deployment sequence

1. Record `git status --short` and current HEAD.
2. Run `git diff --check`.
3. Derive required deployment values from the current running container/environment/mounts.
4. Validate required host files without reading secret contents.
5. Run Compose configuration validation from the authoritative Compose directory/file.
6. Build `jason-runtime:local`.
7. Only if build succeeds, recreate/start the `jason-runtime` service.
8. Poll the health endpoint/container health until healthy or a bounded timeout occurs.
9. Report each return code and final container state.
10. If any step fails, report the error and continue the interactive troubleshooting session; do not terminate the user's shell/session.

## 2026-08-12 deployment proof

The semantic resource-inquiry changes were validated before deployment. The final build completed successfully, the container restarted successfully, and the runtime health check passed.

The deployed worktree remained intentionally uncommitted at HEAD `25bc07a`; deployment success must not be confused with Git durability. The code changes therefore still require a separately authorized commit/push if they are to become durable repository state.

Final functional proof through Teams:

`AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm.`
