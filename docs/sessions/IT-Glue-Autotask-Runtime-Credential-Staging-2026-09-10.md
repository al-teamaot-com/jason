# IT Glue + Autotask Runtime Credential Staging — 2026-09-10

## Purpose

Define the source-only deployment seam that lets the non-root `jason-runtime`
container consume the already-provisioned, read-only IT Glue and Autotask
OpenBao AppRoles without changing the protected bootstrap files or combining
provider identities.

This checkpoint does **not** stage production credentials, contact OpenBao,
restart a service, activate a provider, expand the MCP surface, or merge the PR.

## Existing runtime boundary

`infrastructure/jason-runtime/compose.yaml` runs Jason Runtime as UID/GID
`1000:1000`, with a read-only root filesystem, dropped capabilities, and
provider AppRole files mounted individually as read-only files beneath
`/run/jason-secrets/openbao`.

The provider-read runtime resolves IT Glue and Autotask through distinct paths:

- `/run/jason-secrets/openbao/it-glue/role_id`
- `/run/jason-secrets/openbao/it-glue/secret_id`
- `/run/jason-secrets/openbao/autotask/role_id`
- `/run/jason-secrets/openbao/autotask/secret_id`

The corresponding bootstrap AppRoles remain independently provisioned:

- `/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/{role-id,secret-id}`
- `/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/{role-id,secret-id}`

The bootstrap files are not suitable as direct bind-mount inputs for the
UID/GID `1000:1000` runtime because they are intentionally root-owned and
private.

## Staging design

`tools/stage_provider_read_runtime_credentials.py` provides two explicit modes.

### `--check-only`

Metadata validation only:

- requires each bootstrap source to be a regular file;
- rejects symlink sources;
- requires the approved source owner;
- rejects group/world-readable source files;
- does not open or read credential content;
- creates no destination directories or files;
- contacts neither OpenBao nor a provider;
- prints no credential value or credential hash.

### `--stage`

A separate, explicit production action:

- requires effective UID 0;
- validates all source metadata before reading any credential;
- opens source files with `O_NOFOLLOW` when supported;
- revalidates file identity and permissions after opening;
- bounds each credential file to 16 KiB and rejects empty files;
- copies credential bytes only into a private host runtime directory;
- creates root-owned mode `0700` host staging directories;
- creates leaf runtime files owned by UID/GID `1000:1000`, mode `0400`;
- uses same-filesystem temporary files and atomic installation;
- denies overwrite by default;
- permits replacement only with explicit `--replace-existing`;
- removes partial initial-stage output if a later copy fails;
- never prints or hashes credential values;
- does not contact OpenBao or any provider.

The default host staging root is:

`/run/jason-runtime-credentials/openbao`

Because the host staging directories are root-owned mode `0700`, the runtime
leaf files are not traversable by the ordinary host user even though their
numeric owner matches the container UID. Docker binds the individual files
read-only into the container's established credential destinations.

The host staging area is under `/run`, so it is intentionally ephemeral across
host reboot. A deployment after reboot must restage from the protected
bootstrap source.

## Compose contract

The runtime Compose file now requires four additional host-path variables:

- `JASON_IT_GLUE_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_IT_GLUE_OPENBAO_SECRET_ID_HOST_PATH`
- `JASON_AUTOTASK_OPENBAO_ROLE_ID_HOST_PATH`
- `JASON_AUTOTASK_OPENBAO_SECRET_ID_HOST_PATH`

They identify files only; they never contain RoleID or SecretID values.

The expected staged values are paths under
`/run/jason-runtime-credentials/openbao/{it-glue,autotask}`. Compose mounts the
four files read-only into the provider-specific in-container paths above.

This deliberately makes first provider activation explicit. Existing
`jason-ops.sh` does not synthesize these new values from bootstrap material.
Until a runtime has intentionally been deployed with these mounts, an operator
must supply the staged host paths. Missing variables cause Compose rendering to
fail closed.

## Least-privilege properties

IT Glue and Autotask remain separate AppRoles with separate OpenBao policies.
No shared provider-read AppRole is introduced.

A single `jason-runtime` process necessarily has filesystem access to the
provider identities mounted for the connectors it hosts. That does not combine
their OpenBao authorization: each resolver authenticates with its own AppRole,
and OpenBao policy remains provider-scoped.

Credential staging is local transport of authentication material only. It does
not grant Jason capability authority, client scope, provider activation, or
write authority. Those remain controlled independently by Jason governance and
Central Orchestrator.

## Production checkpoint

Before any actual `--stage` operation or runtime recreation:

1. Verify the final PR head and relevant CI.
2. Run `--check-only` on the Jason host using root only for metadata access.
3. Confirm no bootstrap mode/owner change and no destination write occurred.
4. Obtain explicit production approval.
5. Stage the four runtime files.
6. Render Compose with the four staged host-path variables.
7. Recreate only `jason-runtime`.
8. Verify health and read-only provider capability behavior.
9. Keep MCP provider activation and PR merge as separate governed checkpoints.

No production action in steps 5–9 is authorized by this document.
