# J-Assist — Existing AWS relay validation handoff

**Date:** November 12, 2026
**Reported completion:** 10:29 AM ET
**Scope:** Read-only Caddy inspection and offline candidate validation
**System:** Existing `Jason-Teams-Relay`, EC2 instance `i-0b0bb56884acb565c`, AWS account `887670144825`, `us-east-1`
**Authority:** Prior AOT Owner request to inspect and validate; **no approval to apply changes**

## Source and confidence

The Project Owner supplied the following **completion report from the authenticated
Work/CloudShell session**. This document preserves that report accurately.
The current Chat-connected shell and GitHub connectors did **not** expose the
Work session's raw Caddyfile, adapted JSON, command transcript, or nine negative
test case outputs. Therefore the findings below are **Work-session-reported
verification**, not independently re-executed tests by this chat. Do not
fabricate source hashes, exact shell commands, identities or test IDs.

## Recorded results

| Gate | Reported result | Meaning |
| --- | --- | --- |
| Actual running Caddy version | **v2.11.4** | Current relay version identified, not inferred from a package repository |
| Live Caddyfile integrity | **Unchanged** | Read-only inspection did not modify the live file |
| Running-versus-adapted baseline | **Match** | Live active routing matches freshly adapted original configuration |
| Full proposed candidate validation | **Pass** | Complete candidate was validated offline, without loading it into Caddy |
| Existing MCP route preservation | **Equivalent** | Preserved after accounting for Caddy-generated group-label renumbering |
| Existing Teams route preservation | **Equivalent** | Preserved after accounting for the same generated label differences |
| Negative controls | **9/9 pass** | Work report attests all nine checks passed; individual case IDs/logs not supplied here |
| Live Caddy configuration/process | **Unchanged** | No config write, reload, restart, or route activation |
| New AWS resources or IAM permissions | **None reported** | Separate Owner statement and previously observed read-only AWS use |

### Why group-label renumbering matters

A new Caddy route can change generated internal group labels in adapted JSON
without changing the actual routing policy. The Work session evaluated
*semantic routing equivalence* rather than declaring the entire adapted JSON
byte-identical. The existing
`infrastructure/jassist-pilot/verify_caddy_adapted.py` is a strict-delta
helper and should not be represented as proof it directly accepted the
live Caddy candidate unless the actual Work transcript shows how
generated labels were normalized and which safety fields were protected.

## Evidence required for an immutable activation review

The Work result is sufficient to update the **relay-verification status to
reported PASS**. Before an exact-revision activation review treats it
as *independently reproducible evidence*, attach or cite the following
from the already-completed Work session, without re-running or changing the relay:

1. Redacted original active Caddyfile and its SHA-256; readback identity of
   the running instance and Caddy v2.11.4.
2. Original freshly adapted Caddy JSON and SHA-256, plus the active runtime
   configuration comparison result.
3. Candidate Caddyfile and candidate adapted JSON SHA-256, plus successful
   complete `caddy validate` result.
4. Semantic MCP/Teams route-equivalence comparison, including handling of
   generated group labels; no weakening of host, TLS, authentication,
   or trusted proxy/upstream boundaries.
5. Nine negative test names and pass/fail evidence, with failure criteria.
6. Redacted execution/session reference and the observation that the running
   file, process, and AWS resources/permissions were not changed.

**Do not invent any of these missing hashes or artifacts.** Their absence
from this conversation does not negate the Work result but must be visible
in the promotion packet.

## Production boundary and remaining gates

**Relay verification:** Reported **100% complete** on November 12.
**Pilot activation:** **NOT authorized**, **NOT deployed**.

Separate requirements still pending or not independently read back:

- Current live Entra SPA/Graph consent and AOT technician membership
  in configurable `AOT-Jason-JAssist-Users`.
- The governed Datto numeric device-ID/native-UUID read integration from
  draft PR #2456 and its current AOT-site device readback.
- Provisioned least-privilege scoped OpenBao keys and writable encrypted
  evidence storage with 120-second retention and audited purge.
- Independently approved screenshot screening. Present source allows only
  exact, preapproved synthetic/non-sensitive frames; this is not general DLP.
- Approved isolated pilot HTTPS receiver/route and same-technician MCP
  image tool registration, with real controlled screenshot acceptance.
- Exact candidate SHA, reviewed scope SHA256, current rollback SHA and
  independent governance/Owner authorization for any change to the existing
  relay or production environments.

Nothing in this relay handoff replaces those controls. Preserve existing
MCP, Teams, ticket processing, production freezes and automatic promotion
holds unchanged.
