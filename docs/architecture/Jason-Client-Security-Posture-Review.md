# Jason Client Security/Posture Review

## Section Goal
Allow Jason to select one authorized client, collect authoritative governed evidence, compare that evidence with AOT's managed-security baseline, and produce an evidence-backed gap report and improvement proposals without making configuration changes.

## Classification contract
Every control must resolve to exactly one of:
- `confirmed_good` — authoritative current evidence matches the baseline;
- `confirmed_gap` — authoritative current evidence contradicts the baseline;
- `unknown` — the source is available but current evidence does not establish the answer;
- `not_applicable` — the control is explicitly not applicable to the client/resource;
- `evidence_unavailable` — Jason lacks the authoritative provider/read surface needed to establish the answer.

Missing evidence must never be interpreted as healthy. Historical memory may guide investigation but cannot independently establish current posture.

## Initial AOT baseline families
The deterministic evaluator defines controls for BitLocker, managed AV, managed EDR, supported OS, DRMM monitoring health, VulScan coverage, DNSFilter coverage, managed backup coverage, recent backup success, Microsoft MFA posture, Conditional Access baseline, and documentation completeness.

This is an evidence model, not a claim that every provider surface is already available. For example, recent successful backup remains `evidence_unavailable` until the Endpoint Backup API is integrated; Microsoft MFA/Conditional Access remain unavailable where tenant consent does not authorize those reads.

## Safety and authority
The review is read-only. A `confirmed_gap` creates an improvement proposal; it does not authorize remediation. Existing ticket/company client boundaries remain authoritative. Provider reads must retain their own evidence timestamp and correlation/source reference. Cross-client evidence is prohibited.

## Next production slice
1. Bind a review to an exact Autotask company/client identity.
2. Map existing governed DRMM/Autotask/IT Glue evidence into normalized control observations.
3. Run the first review against a controlled AOT/XYZ test client.
4. Verify unavailable sources remain visibly unavailable rather than guessed.
5. Add a report surface and Grafana aggregate telemetry only after the evidence mapping is production-proven.
