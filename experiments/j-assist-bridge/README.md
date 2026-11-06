# J-Assist governed session bridge — preproduction only

This module establishes a **server-side authority contract** for a future
technician-initiated bridge. It deliberately does **not** connect the Chrome
extension or enable a network listener. It is not production-enabled.

## Existing constraints verified

The Jason runtime HTTP endpoint currently accepts signed Teams conversations
and does not attest Chrome technicians or Datto Web Remote sessions. Reusing
that endpoint for extension screenshots would not meet AOT's governance.

## Required adapter contract

1. Server-side trusted identity adapter returns the authenticated AOT technician
   and organization tenant ID. **Never accept these from browser JSON.**
2. Server-side provider-backed authorization verifies the technician's native
   Datto RMM access to the exact device immediately before each request.
3. Start requires explicit user consent, returns a short-lived session-bound
   credential, and binds one technician, tenant, and Datto device.
4. Stop, expiration, permission loss and changed session immediately revoke access.
5. Only lifecycle metadata is accepted in this initial module. **No screenshot,
   raw PowerShell output, browser token or page content may be transmitted yet.**
6. Before content enablement, implement and independently accept private network
   TLS ingress, authentication, authenticated origin binding, screenshot/text
   redaction, data minimization, audit retention, rate limits and proof that
   another technician cannot read the session.
7. No command execution or endpoint mutation is part of J-Assist v1.

## Validation

Run: `python3 -m unittest discover -s experiments/j-assist-bridge/tests -v`

Unit tests use synthetic trusted identities and synthetic provider authorizers.
They are not live provider-backed acceptance or proof of real identity binding.
The browser extension remains entirely local-preview only.

## JKD-001 integration (preproduction)

`jkd_authority.make_jkd_datto_authorizer` calls Jason's existing
`IdentityAuthorityService.evaluate` on every session request and requires an
explicit `j_assist.session.observe` OBSERVE grant, plus a separately injected
provider-backed **native Datto device-access** check. Neither an AOT standing
read grant nor a browser-declared identity is sufficient. Denials and revocations
fail closed. No new grant, new role or token is provisioned by this code.

The native Datto role/permission query and Microsoft identity attestation are
still missing production adapters. Tests use real JKD service objects but
synthetic identities and provider permissions. These tests do not prove an
actual Datto technician's access.
