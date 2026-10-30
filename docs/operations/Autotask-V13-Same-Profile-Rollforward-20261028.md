# Autotask same-profile governed production rollforward

Native release preflight permits the live runtime or MCP service to be on either the exact source-declared read profile or the source-declared last-known-good rollback profile. Both profile names must be present in the immutable source declaration. Any third/unrecognized live profile fails closed. This addresses a v13-to-v13 release after v13 is already installed; it does not change selected provider access, write authority, rollback SHA, or deployment approval requirements.

Both runtime and MCP production deploy scripts share the same profile predicate, tested using fake Docker output without production mutations (`tools/tests/test_autotask_release_deploy_profile.py`). Native release manager, protected-source checks and exact owner authorization remain required for promotion.
