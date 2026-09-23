# Jason Datto RMM Execution OpenBao Staging Success — 2026-09-15

## Purpose

This record captures the successful completion of the approved Phase 3 OpenBao staging for the separate Datto RMM execution identity after the earlier fail-closed CAS and policy-response-shape recovery work.

No provider credential value, OpenBao token, Linux password, Datto API key, Datto API secret, RoleID, SecretID, or provider-native object ID is recorded here.

## Authorization boundary

Phase 3 provider identity and containment work was explicitly approved by the owner.

This staging does not authorize or activate a Datto quick job, runtime execution surface, arbitrary provider writes, production MCP/runtime recreation, or PR merge/readiness. The first live component execution remains a separate approval boundary.

## Successful staging evidence

The guarded recovery was pinned to authoritative source `f5cb2c418d774c771e11102b403f284fcf1a14f1` and validated recovery code head `6becc09bf960eb9d0a1807cedc7dc466c214a0fc`.

The run proved before mutation:

- authoritative remote head matched the expected source;
- isolated checkout was pinned, fsck-clean, and worktree-clean;
- the validated recovery code was an ancestor of the execution head;
- no post-CI drift existed in the recovery scripts, recovery tests, execution policy, or focused workflow;
- the live-shape recovery scripts compiled and passed a local smoke test for the observed OpenBao `data.policy` response shape;
- OpenBao, MCP, and runtime were running;
- the execution bootstrap target was absent;
- the final authoritative source pin still matched immediately before recovery.

The recovery then:

- authenticated to OpenBao through a temporary administrative session;
- collected the already-created separate Datto execution API key and API secret through hidden prompts;
- verified the existing Datto execution ACL policy against approved source;
- verified the existing Datto execution AppRole against approved source;
- created the execution KV record with the CAS-required new-record contract;
- verified the execution record as an isolated version-1 record;
- verified the execution AppRole can read only the execution credential and is denied access to the existing Datto read-only credential;
- created protected bootstrap AppRole material atomically;
- re-verified that the existing Datto read-only secret remained unchanged;
- explicitly revoked the temporary administrative token.

Post-recovery host checks proved:

- protected bootstrap material exists with the expected root-only ownership/modes and expected file set;
- OpenBao, MCP, and runtime container identities did not change;
- all three services remained running;
- no service restart occurred.

The final run reported:

- `OPENBAO_EXECUTION_STAGING=PASS`;
- `EXECUTION_LOGICAL_SECRET=datto_rmm.execution`;
- `EXECUTION_SECRET_VERSION=1`;
- `EXECUTION_APPROLE_ISOLATION=PASS`;
- `READONLY_SECRET_UNCHANGED=PASS`;
- `DATTO_PROVIDER_CONTACTED=NO`;
- `RUNTIME_ACTIVATION=NO`;
- `PROVIDER_WRITE_ACTIVATION=NO`;
- `COMPONENT_EXECUTION=NO`;
- `MCP_RESTARTED=NO`;
- `RUNTIME_RESTARTED=NO`;
- `OPENBAO_RESTARTED=NO`;
- `JASON_STEP_RC=0`.

## Current state

OpenBao staging for `datto_rmm.execution` is complete.

Production Jason remains read-only and has not been given an activated Datto execution route. The existing `datto_rmm.readonly` credential remains separate and unchanged. No Datto component or quick job has been executed by this workstream.

## Next Phase 3 proof

The next approved Phase 3 step is a harmless provider-contact proof using the staged execution identity:

1. authenticate to Datto RMM with the separate execution credential;
2. perform only GET requests after OAuth token acquisition;
3. prove a no-restriction system-status read succeeds;
4. prove Global Settings-gated account, account-device, and account-component reads remain denied under the intended minimum execution API Security Level;
5. print no credential, bearer token, or provider response body;
6. perform zero provider mutation requests and zero component execution;
7. leave runtime execution disabled.

Positive Device Visibility and API Component Level containment require provider-native examples that exercise those restrictions without mutation. Those proofs remain separate from the negative Global Settings permission proof and must not be inferred merely from successful authentication.

## Related records

- Credential staging history: `docs/operations/Jason-Datto-RMM-Execution-Credential-Staging-2026-09-15.md`
- Live ACL policy response evidence: `docs/operations/Jason-Datto-RMM-Execution-Live-Policy-Shape-Diagnostic-2026-09-15.md`
- Workstream: `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
- Draft PR: #184
- Capability objective: issue #183
