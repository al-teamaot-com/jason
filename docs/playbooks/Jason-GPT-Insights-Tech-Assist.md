# Jason GPT Insights - Help Desk Tech Assist

**Version:** 0.1.0  
**Status:** Production scope; durable owner promotion required  
**Mode:** Advisory, internal-note only

## Section Goal
Give an AOT technician useful, evidence-grounded help on legitimate Help Desk tickets that Jason cannot autonomously resolve, without moving the ticket, claiming it, performing remediation, or asking a human for facts Jason can obtain itself.

## Trigger
A ticket is in Help Desk I or Help Desk II and no promoted autonomous remediation playbook applies.

## Core standard
Jason must not ask a technician or client for information it can reasonably obtain through authorized evidence sources. Before identifying a human question, Jason must exhaust relevant ticket evidence, authoritative provider reads, approved read-only diagnostics, and bounded same-client correlation.

## Note contract
- Create at most one base internal note titled `GPT Insights`.
- Do not create duplicate base notes after restart or local-state loss.
- Add a new note only when material evidence changes, titled `GPT Insights - Update <date/time>`.
- Do not add updates for cosmetic changes, repeated evidence, or merely newer timestamps that do not change guidance.
- GPT Insights notes are machine-generated advisory evidence and never count as technician-authored work.

## Useful evidence
Collect only information that helps reduce technician effort. Examples include associated device, online/offline state, last-seen evidence when available, OS, active wired/Wi-Fi evidence for network complaints, bounded related-ticket history, and correlation evidence that may indicate a broader issue.

## Unknown requests
If Jason cannot confidently classify or process the reported request, the note must say so. It must not invent a root cause or fill the note with generic troubleshooting. Human follow-up is requested only for information Jason cannot retrieve.

## Recommendations
Recommendations must be evidence-grounded and concise. PowerShell guidance must default to read-only diagnostic one-liners. Disruptive or modifying actions remain outside this scope.

## Governance boundary
Allowed mutation: `service.ticket.note.create` only. No ticket status/queue updates, no client communication, no component execution, no remediation, no reboot/logoff/service restart, and no generic modifying PowerShell.

## Learning / API conservation
Validated recurring patterns may be reused locally when their evidence requirements and exceptions are satisfied. Cached guidance must never substitute for current facts: online state, last seen, active connection type, alerts, and other time-sensitive evidence must be refreshed before the note is produced.

## Acceptance tests
1. Unsupported Help Desk ticket receives one base GPT Insights note after exact durable promotion.
2. Same ticket does not receive duplicate base notes.
3. Materially changed evidence can generate a timestamped update.
4. Network ticket resolves wired/Wi-Fi from endpoint evidence when available rather than asking the tech.
5. Unknown request documents uncertainty without fabricating a cause.
6. No ticket update or disruptive action occurs from this playbook.
