# Jason P0: smallest justified effective remediation

## Owner decision (2026-10-28)

Across all approved device and client management systems, including Datto RMM, Datto EDR/AV, BackupIQ, DNSFilter, Microsoft/Entra and future supported providers, Jason may propose a non-read-only operation only when evidence supports a reasonable expectation that it will resolve or improve the issue. A technician's instruction and authorization permit *consideration* of the exact proposed action; they do not obligate Jason to execute an ineffective, unnecessary or disproportionately disruptive change.

**Use the least disruptive effective intervention.** A stopped Print Spooler usually calls for a targeted spooler service restart, not a workstation reboot. If the service restart fails, or independently observed evidence shows reboot is required, an exact authorized reboot becomes eligible. When high-risk containment is urgently necessary, a narrowly targeted EDR containment action may be more appropriate than a benign but ineffective service repair; it is still subject to explicit approval when it interrupts access.

## Shared execution rule

The `least_disruptive_policy` evaluator operates at the common governed MCP mutation boundary for registered `endpoint.*`, `automation.component.execute`, `backup.*`, `dnsfilter.*`, `management.*`, `identity.*`, `security.*` and `network.*` operations. Its input is a reserved control-plane object `jason_remediation_review` inside `execute_governed_capability.arguments`, which is stripped before provider execution. Ordinary Autotask ticket updates/notes, notifications and purchasing paperwork are administrative actions, not endpoint remediation, and retain their existing controls.

For an actual modifying management command, Jason must include:

```json
{
  "jason_remediation_review": {
    "decision": "recommend",
    "target_id": "device-uid-from-the-current-ticket",
    "problem": "Print Spooler is stopped and print jobs cannot complete.",
    "evidence_refs": ["correlation-id-from-current-governed-read"],
    "expected_improvement": "Restore the Print Spooler without restarting Windows.",
    "verification": "Re-read service status and verify printing resumes.",
    "narrower_options": []
  }
}
```

For a reboot or endpoint isolation, each narrower plausible remedy must be considered with a disposition of `viable`, `attempted_failed`, `not_applicable`, or `unsafe`; reasons other than viable require evidence references. A still-viable narrower remedy **blocks** the broader action, even if the technician approves. Reboots for printing issues must explicitly address a Print Spooler/service alternative. Any host/network disruption and any action whose service impact is uncertain requires explicit technician approval for that particular instance. Existing exact-argument approval, technician identity, tenant isolation, approved provider scope, idempotency, retry bounds, audit and post-action verification are **additional** gates; this assessment does not grant or bypass any of them. Where a deterministic standing-safe read-only diagnostic is already approved server-side, no mutation justification is added.

## Evidence limitations and expectations

Review fields are Jason's *proposed reasoning*, not independently authenticated source evidence. Strings in `evidence_refs` are not proof of a real finding; they are references to be checked in the underlying governed provider read trail. The decision layer binds the management operation to its canonical argument fingerprint and verifies an exact target selector, and stamps the policy identifier into the governed request for audit. The existing provider adapters/verification checks remain responsible for actual provider evidence and outcome verification. **Do not equate passing this assessment with a verified technical resolution or with technician approval.** Additional source-evidence receipt validation may be added later without granting broader write access.

If Jason cannot explain the expected improvement, supply prior evidence references, name a verification method, or resolve a viable narrower alternative, it must decline or request missing diagnostic information. It must not invent observations, claim an action is safe based solely on its name, substitute an unspecified generic reboot, or silently choose a broader operation because it is easier to run. For a modified system, read back the result, record an internal note with evidence and action identity, and escalate only when narrower permitted options have failed or are inappropriate.

## Acceptance

Regression tests verify that: technician-approved but unhelpful actions are refused before approval/provider execution; restarting the spooler with exact approval may proceed; rebooting with a still-viable spooler fix is refused; a reboot can be proposed after a failed narrower repair with evidence and exact authorization; urgent EDR isolation can be justified with evidence; backup and DNSFilter changes require a benefit and verification; a proposed review cannot be reused across different targets; unknown management components default to a potentially service-disruptive classification; and read-only diagnostics/ticket notes retain their normal pathways. Production freeze and exact-SHA deployment approval remain mandatory.
