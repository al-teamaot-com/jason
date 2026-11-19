# Governed preproduction Owner read-only status — scoped source correction

## Section Goal
Permit the independently authenticated, unscoped AOT licensed Owner
`al@teamaot.com` to **read** two Jason preproduction acceptance readiness
statuses without converting that Owner's routine requester identity into
`person-al` or granting unrestricted authority.

## Authoritative installed state (read-only verified)
- `jason-mcp-pilot` uses legacy `JASON_AOT_ADMIN_APPROVER_PROFILE` (empty)
  and exact admin owner allowlist `person-al`.
- Its active Entra binding store has licensed Owner Entra object
  `bee80bdc-ffb0-4c50-b453-c09d4d411f5f` bound to the active unscoped
  requester `person-entra-bee80bdcffb04c50b453c09d4d411f5f`.
- Privileged Entra object `c848022d-e13b-4457-84b0-e2f5c00dcaf6` remains
  bound to `person-al` using `al_admin@teamaot.com`.
- Entra read-only directory evidence identifies `al@teamaot.com` and the
  licensed Owner UUID. The independent MCP authenticated bearer claims must
  still be checked on every call; source evidence alone is not proof of the
  current ChatGPT Jason OAuth token.
- An existing manual break-glass binding recovery correctly rejects the
  regular Owner (`RECOVERY_OWNER_ALREADY_BOUND`). It must **not** be used
  to override or steal the privileged binding.

## Narrow source change
Readiness-status tools only:
- `provider_health_canary_status`
- `autonomy_execution_acceptance_status`

The source calls the existing `_release_approval_owner()` verifier (signed
Entra bearer -> exact tenant/object -> active bound Jason human) and rejects
client-scoped identities. No extra registry/config, alias, identity migration,
credential access or new engine is created.

**No approval or execution path changes.**
The following continue to use `_authority_admin_owner` and still reject the
regular licensed Owner:
- exact authority grant/revoke/list administration
- provider canary grant/revoke
- autonomous write acceptance approval/revoke/run
- any production release, deployment or JSON activation

## Source tests and rollback
Targeted tests include licensed Owner status acceptance; wrong tenant, object,
principal, assurance and client scope rejection; existing admin-role, grant
administration, catalog grant, lifecycle and release identity regressions.

Rollback: revert this scoped source commit prior to any separately governed
native MCP release. No on-host activation is part of source merge.

**Classification:** Identity/authorization source change; require independent
security review and protected CI before source merge. Native MCP release
requires exact SHA, scope, rollback and separate production authorization.
Production freeze, PMv4 Ticket Core and Stage E remain unchanged.
