# Jason Technical Note Standard v1

Status: Approved operational standard  
Owner: AOT / Project Jason  
Effective: 2026-10-01

## Purpose

A technician should be able to open any ticket Jason touched and know, without
learning the playbook first, where to find the current condition, issue scope,
findings, evidence, actions, verification, and next action.

The same category of information MUST appear under the same heading and in the
same order regardless of ticket type, provider, or playbook.

## Canonical section order

Every technician-facing Jason technical note MUST contain these sections in this
exact order:

1. `STATUS`
2. `ISSUE`
3. `DEVICE / SCOPE`
4. `FINDINGS`
5. `EVIDENCE`
6. `ACTIONS TAKEN`
7. `VERIFICATION`
8. `NEXT ACTION`
9. `JASON STATE`
## Section contract

### STATUS

One or two lines describing the condition now: confirmed, resolved, waiting,
blocked, or requiring human review. STATUS is not a copy of the alert title.

### ISSUE

A plain-language statement of what Jason is investigating or resolving.

### DEVICE / SCOPE

Authoritative identity and scope. Include the ticket number, company boundary,
hostname/device identity, Autotask configuration item, provider endpoint UID,
and user/contact only when relevant.

### FINDINGS

Jason's technical conclusions, strongest and most actionable first. A technician
who wants the answer should be able to read this section without parsing raw logs.

### EVIDENCE

Provider-backed facts that support the findings: service/patch states, event IDs,
alert IDs, timestamps, job/component identifiers, error codes, and bounded log
or component output. Interpretation belongs in FINDINGS; proof belongs here.
### ACTIONS TAKEN

Exactly what Jason changed, ran, or resolved. If nothing was changed, say so
explicitly. A technician must never have to infer whether Jason mutated a
device, provider object, policy, service, ticket, or alert.

### VERIFICATION

Post-action or post-diagnostic checks proving the current state. If verification
is pending or impossible, state why rather than implying success.

### NEXT ACTION

Mandatory. State the single clearest next step. If Jason owns the next step, say
what he will do and what condition/cadence triggers it. If a technician owns it,
state the required technician decision/action. A completed ticket says that no
next action remains.

### JASON STATE

Machine/technician-readable lifecycle footer. Include playbook, current phase,
waiting/block reason when relevant, and enough state to understand why the ticket
is not currently executing.

## Canonical note titles

Jason uses a bounded title taxonomy so technicians can identify note purpose from
the ticket activity list:

- `Jason - Technical Review`
- `Jason - Work Update`
- `Jason - Remediation Result`
- `Jason - Waiting State`
- `Jason - Human Review Required`
- `Jason - Resolution`
## Note density and update behavior

Jason SHOULD produce one meaningful summary note per work session or material
state transition. Repeated checks that do not change findings, evidence, action,
or next step MUST NOT create ticket-note noise.

Provider evidence may be collected many times internally. That does not require a
new technician-facing note unless the operational meaning changed.

## Safety and evidence rules

- Findings must be traceable to authoritative provider evidence.
- Actions must distinguish observation from mutation.
- Verification must not infer success from job submission alone.
- Unknown or unavailable evidence must be identified as unknown/unavailable.
- Secret-bearing values must never be copied into the ticket note.
- Client-facing communication is a separate governed surface; this standard is
  for technician-facing/internal technical notes unless an approved policy says otherwise.

## Runtime enforcement

The autonomous worker routes technician-facing notes through the shared technical
note renderer. During v1 migration, existing playbook narrative is preserved in
FINDINGS while the renderer guarantees the canonical headings, scope block,
NEXT ACTION, JASON STATE, and bounded title taxonomy.

New and materially revised playbooks SHOULD populate the sections explicitly
instead of embedding multiple categories of information in narrative prose.

## Acceptance criteria

1. Every autonomous technician-facing note contains all nine headings in order.
2. NEXT ACTION is never omitted.
3. DEVICE / SCOPE identifies the ticket and exact known endpoint/CI boundary.
4. JASON STATE identifies the playbook and lifecycle phase.
5. Note titles come from the canonical six-title taxonomy.
6. Existing evidence is preserved during migration.
7. Duplicate unchanged notes remain suppressed by note fingerprinting.
8. No authority, provider-access, or disruptive-action boundary is broadened.