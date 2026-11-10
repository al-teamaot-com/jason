# Release-only Owner identity binding (source preparation)

**Date:** November 10, 2026  
**Status:** Source-only. Not deployed or approved to bypass live production controls.

## Problem and verified evidence

Jason's existing MCP Owner allowlist contains only `person-al`. The licensed
regular account `al@teamaot.com` is independently bound to the active Jason
principal `person-entra-bee80bdcffb04c50b453c09d4d411f5f` under Entra
tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`, object ID
`bee80bdc-ffb0-4c50-b453-c09d4d411f5f`. Native
`owner_identity_recovery.py` refused remapping because the existing source
principal holds execute/administer grants. Those grants must not be moved,
revoked or implicitly inherited by another principal.

## Narrow replacement

`authorized_release_owner` accepts this **exact** bound, already-authenticated
regular Owner subject for `approve_release_candidate` only. It requires
AOT organization, the existing validated Entra OAuth bearer assurance, exact
tenant/object ID and the exact Jason subject. The MCP security middleware
must have validated token issuer/signature/audience/expiry, tenant and active
identity binding before evaluating the additional release-specific predicate.

No modification is made to the global Owner/admin allowlist, grants,
tenant identity storage, privileged account, Datto component approval,
execution permissions or other MCP Owner-only tools.

## Next integration and release gates

This is not an alternate unverified chat approval. The existing release
request remains bound to a production-eligible exact commit SHA. Production
release still requires an independently verified one-time Owner decision,
source/rollback/scope/manifest binding, passing technical gates, and the
protected freeze/breaker boundaries. The **separate Teams-only Release Manager
and root reconciler requirements have not yet been retired**. Do not deploy
this source as though those remaining blockers were solved.

Historical V2 production, its byte-identical freeze and the open root
breaker remain unchanged by this source preparation.
