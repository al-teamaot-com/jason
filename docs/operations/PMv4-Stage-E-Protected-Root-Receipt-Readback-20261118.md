# PMv4 Stage E: protected root acceptance evidence

**November 18, 2026 - source-only root attestor, NOT deployed and NOT retirement authority.**

The installed Stage C independent Ticket Core, Stage D independent read-only
Runbook Management and A1 v5 network-disconnected shadow have all passed
their exact Owner-bound acceptance procedures. The unprivileged Stage E
checker can confirm live service health but cannot independently read the
root-owned 0600 immutable acceptance receipts. That missing check is a
real gate, not proof that the services are absent.

The source-only helper tools/pmv4_e_root_receipt_readback.py defines one
fixed, strict, read-only acceptance check for a later governed Stage E
retirement preflight:
- Stage C root-owned accepted receipt for candidate
  7aaa2c3fc3ac51279c3488a16ab39b6e7a03007e, with two distinct
  scan-cycle IDs, no database relocation, zero MCP restarts.
- Stage D root-owned accepted receipt for source
  6dc78887b636dce5066871a3076bfe75bcd84ad3 and reviewed scope
  72a0a13156aa29eab559d36ff44e56e38dc5ee22f0b3ca6b0cfc3c95ae42cf01,
  native drift pass, no provider writes, no runtime/MCP/Ticket Core restart
  and unchanged freeze.
- A1 v5 root-owned accepted native receipt for
  9859463e5255ecf7040de21d73e9f4062b46a18e, exact prior release
  75f2b4c0c48a15bd17d700b9f039fe56623e3f52 and exact Owner consent
  owner-mcp-e547ca784f76418391ca5bd938afd237, SHA-bound manifest,
  reviewed scope, freeze and no PMv3/provider mutation.
- The v5 root-owned audit must be a full, contiguous SHA-256 chain from
  begin through committed, tied to the same exact Owner and source,
  with no rollback/requires-review events.
- The installed active protected desired-state bytes must match the
  exact SHA-256 of the accepted Stage D post-install policy:
  4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953.
  At this stage it still requires all six legacy release/engineering units
  and allows only the separately authorized Runbook Management unit delta.

No generic root directory scan, configurable path, attacker-controlled
candidate revision, shell invocation, Docker command, systemctl mutation,
provider call, output of secret fields or unsigned Owner grant is supported.
All protected files must be root-owned, singly linked, nonsymlink regular
0600 files. The CLI denies execution outside UID 0; it prints only a
minimal nonsecret status. A protected Stage E installer will have to stage
and hash-pin this helper before invoking it; direct execution from a
mutable source worktree is not production release authorization.

31 offline fail-closed tests cover the accepted fields, wrong candidate,
scope and prior SHA, replay ambiguity, nonunique scan cycle, forbidden
provider writes/restarts, altered audit chain, noncommitted transaction,
changed protected desired state and unprivileged invocation.

**This tool can only verify pre-retirement evidence. It always returns
retirement_authorized=false.** PMv4 engineering/release controller parity
and a new exact authenticated Owner retirement release remain mandatory
before touching legacy PMv3 timers or desired-state policy.
