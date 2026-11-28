# Staff read failures — investigation and correction preparation

Date: 2026-11-12. Scope: Lindsey Collins and Adam Navrat only; Al's requests are excluded from the evaluated failures. No production deployment, access-grant change, secret rotation, authorization-mode change, or native-permission proof activation is authorized by this package.

## Verified evidence

The review traced 11 terminal orchestration records from the November 5–12 window: Lindsey had nine failed operations and one denied request; Adam had one failed operation. These are operation attempts, including retries, not counts of separate incidents or dissatisfied users.

Every retained execution context for these attempts recorded `outcome=allowed`, `requested_mode=observe`, authenticated Entra bearer assurance, and an organization-level operational read grant. Both Jason identities were active. Governed Autotask resource searches independently matched Lindsey and Adam to active Employee records (resource IDs 29682899 and 29682896). Active employee status and Jason read authority do not prove native Autotask permission to release time-entry data.

| Person / operation | Time (Eastern) | Observed outcome | Correlation evidence |
| --- | --- | --- | --- |
| Lindsey / DNS query investigation | Nov 5, 3:59 PM | Connector authorization denied before a connector-requested event | `corr_mcp_56311af3ee5d4f01960569f18a7859b7` |
| Lindsey / attachment metadata | Nov 6, 10:49 AM | Denied: client context required | `corr_mcp_29adadab4688460caf9f86d6d457ff19` |
| Lindsey / ticket search | Nov 6, 1:20 PM | Three invalid-argument failures | `corr_mcp_c050d7895db3450db49c260822022906`, `corr_mcp_089d9775d6c9482db5107adde4279bb0`, `corr_mcp_fbeec4e9c7b7455fabde83712420159b` |
| Lindsey / ticket labor | Nov 6, 1:22 PM | Generic invocation failure before a connector-requested event | `corr_mcp_5b9d59259c774fbfbffee6d9bde273c8` |
| Lindsey / directory user search | Nov 6, 2:33 PM | Two invalid-argument failures | `corr_mcp_2dbaafb9d72c4dfe94ef83678cdd8af5`, `corr_mcp_8e9e9f253a2949d7a9e3e135756eee02` |
| Lindsey / ticket search | Nov 9, 8:18 AM and 10:19 AM | Microsoft credential resolution failed | `corr_mcp_14ca44525b1f44db93d94e17fca18f97`, `corr_mcp_e63d274583ed4711be22b11b68ea79d6` |
| Adam / ticket labor | Nov 11, 12:15 PM | Generic invocation failure before a connector-requested event | `corr_mcp_0908677771a2457a874c8687da788c61` |

Later successful ticket searches and directory-user searches exist for Lindsey. No successful labor read for either staff identity was found in the reviewed window. Successful operations do not prove that the original failed request completed or satisfied the user.

The retained orchestration payloads do not contain the original call arguments or the original exception text. Exact historical invalid selectors, requested DNS company/network, ticket IDs and underlying credential cause cannot be reconstructed from these records. No fabricated replay inputs or historical root causes are asserted.

## Current runtime and source

Running runtime image observed: `jason-runtime:release-d1b8c196dadd-bb7d28ebd5e5`; source revision label `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. This is an observed baseline, not an independently approved rollback candidate.

The running authorization mode is `jason_managed`; native time-entry proof is absent. The current time-entry authorizer explicitly requires both impersonated mode and `JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN=verified`, and raises a plain PermissionError otherwise. Central Orchestrator converts that untyped exception to `CAPABILITY_INVOCATION_FAILED`. This current-path defect is verified; it is consistent with, but does not conclusively identify, the historical labor failures.

An isolated branch was created from fetched `origin/main` revision `387063db0c1f633529b3ecb6920da6a72a64dc03`. Unrelated dirty development in the original checkout was preserved.

## Prepared corrections

1. Preserve the time-entry refusal and report `AUTOTASK_TIME_ENTRY_REQUESTER_PERMISSION_NOT_PROVEN` through a typed PermissionError. No extra access is created.
2. Report fixed validation codes for malformed Autotask search pagination/filter/range calls and Microsoft exact-user search selectors. Valid inputs keep the existing transformations; raw searches remain prohibited.
3. Distinguish missing DNS company, forbidden caller scope override, mismatched client scope, and unverified organization/network boundaries. The same checks still reject before provider execution.
4. Preserve fixed OpenBao authentication/transport/HTTP categories through the Microsoft credential wrapper. Unknown failures remain generic. Exception text, secrets, logical paths and provider bodies are not released.
5. Repair an existing regression-test collection defect: rename a parametrized argument called `request` (reserved by pytest). Test behavior and production behavior are unchanged.

These are targeted diagnostics and validation-feedback corrections. They do not claim to restore native labor access, derive new staff client authority, repair a specific lost historical input, or repair an unproven historical DNS/credential cause.

## Acceptance checks

| Area | Required evidence | Disposition |
| --- | --- | --- |
| Staff authority | Retained identity/context, grants and governed active resource lookup | Verified for both staff |
| Labor permission stop | Managed mode, missing/invalid proof stop before provider; code survives orchestration | Automated acceptance included |
| Labor release protection | Even proven-mode fixture without trusted requester binding cannot release | Automated acceptance included |
| Native labor permission | Staff-authenticated positive read and native denial case on exact authorized ticket/company; no service-account substitution | Not verified; remains a release/activation prerequisite for functional labor access |
| Ticket/user validation | Invalid shapes return fixed actionable codes; existing exact/bounded valid calls remain valid | Automated acceptance included |
| DNS scope | Missing/mismatched/unverified/injected scope stops before provider; valid boundary injects authorized networks; cross-boundary response denied | Automated acceptance included |
| Microsoft credentials | Known source categories remain distinguishable; unknown errors stay generic; no secret text in output/audit | Automated acceptance included |
| Attachment context | Missing or mismatched client context remains denied; no organization grant is silently promoted into a new client context | Existing scoped-read checks retained; safe correction requires verified ticket/company context through the existing authority model |
| Shared regressions | Identity authority, information release, provider reads, Autotask impersonation, DNSFilter MCP and Microsoft connector checks | Results recorded with candidate |

## Remaining functional work and release boundary

- Obtain valid requester-native labor authorization evidence, including negative cases, before considering any activation. Do not merely set a global proof flag or change the production authorization mode.
- For attachment requests, establish the exact ticket/company and an independently valid client context. Do not reuse the Owner-only contract-context derivation to grant staff scope.
- Historical malformed-input and DNS failures cannot be assigned exact causes without their missing inputs. The prepared fixed diagnostic codes make subsequent failures distinguishable without logging sensitive request bodies.
- Credential failures later recovered. No evidence presently justifies credential rotation, broad permissions, or a production restart.
- Review the isolated changes, run required CI, then independently verify exact deployment and rollback artifacts before any production authorization request. Because the change touches authentication/authorization-adjacent shared code, use conservative High-Risk release review even though decisions are preserved.

No staff-authenticated provider acceptance has been fabricated. No production access control was weakened.

## Recorded validation

- Initial targeted run: 141 tests passed.
- Final shared regression and targeted acceptance run: 342 tests passed, zero failures/errors/skips across 31 test modules. JUnit evidence: `/tmp/jason-staff-regressions-20261112.xml` (host-local test output).
- The first shared run stopped at the pre-existing reserved pytest parameter; the test-only rename was applied before the final successful run.
- Automated tests use fixtures. They are not staff-authenticated live provider permission proof.

## Concurrent upstream reconciliation

The patch was rebased cleanly onto `6bfdb76bd3e0bbbb11e09b3c213deaec04f1771a`. Its Microsoft group-admin changes added an explicit approval-gated `group-write` profile. The previously unchanged blanket read-only-profile test then failed on this new profile; the test now requires exactly that one approval-gated exception and keeps every other profile read-only. This additional correction is test-only. The final 342-check run includes the updated credential resolver, group-reader/governed-operation checks and OpenBao tests.

Machine-readable acceptance evidence and tested production-file hashes are stored in `docs/operations/evidence/staff-read-failures-20261112.json`. Live staff-native time-entry acceptance remains unverified and no production activation is included.
