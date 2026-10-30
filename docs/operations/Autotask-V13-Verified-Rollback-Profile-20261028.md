# Autotask v13 verified rollback profile

The independently verified production rollback release ce52cc98dd4ebe471b5e11c7cc482466158acada uses the Autotask dynamic schema read profile v13 on both runtime and MCP. Subsequent v13-to-v13 releases must declare v13 for both the source read profile and the actual last-known-good rollback profile.

The earlier source declaration incorrectly named v10 as the rollback profile. This caused the production script to reject the v13 rollback value supplied by the native release manager. The failed release ba1e2284ab5c5c91aeaa6fff56449a21189f5523 stopped at runtime script validation with rollback verified and no rollback errors.

This correction changes only the source-bound profile declaration and tests. It does not broaden provider access, modify requester disclosure policy, change rollback SHA checks, or permit provider writes. Runtime and MCP preflight tests cover a matching v13 LKG and rejection of a mismatched v10 override. A newly reviewed exact SHA is mandatory for deployment.
