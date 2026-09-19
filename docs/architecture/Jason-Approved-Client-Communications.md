# Jason Approved Client Communications

## Section Goal

Make AOT-approved reusable client responses the default source for Jason's client-facing communication. Jason must search the approved catalog first. When no approved template fits, Jason creates or strengthens a durable Communication Template Request and drafts a complete proposed subject/body using the deterministic AOT HTML shell for human review.

## Provider constraint

Autotask's documented REST API exposes Notification History but does not expose Notification Template definitions as a supported queryable resource and does not document a named-template send operation. Jason must not scrape/private-call the Autotask UI or pretend that Notification History contains the approved template body.

Therefore the governed Jason Approved Communication Template Catalog is the authoritative content source until a supported provider read surface exists. Autotask remains the intended operational/template system; the Jason catalog is the governed mirror/library needed for automation.

## Approved catalog

Source/default: `config/communication/approved-templates.json`.

Production path: `/var/lib/jason/communications/approved-templates.json`.

Only entries with `approved=true` may be treated as approved reusable wording. Each entry records template ID/name, purpose key, audience, subject, HTML body, source, review timestamp, owner, and notes.

A matching approved catalog entry always wins over creating a new template request.

## Template gap workflow

When a playbook or communication decision needs client-facing wording:

1. derive the communication `purpose_key` and intended audience;
2. search the approved catalog;
3. if one exact approved template fits, use that content subject to normal audience/send governance;
4. if none fits, create or strengthen one durable Communication Template Request for that purpose/audience;
5. draft reusable content with `PROMPT-COMM-001`;
6. render the structured content through the deterministic AOT HTML shell;
7. store proposed name, subject, rendered HTML, required variables, scenario, and source playbook/run/ticket references;
8. route the proposal for AOT review/publication;
9. never treat the proposed template as approved merely because Jason generated it.

Repeated no-fit occurrences strengthen the existing request instead of creating duplicates.

## AOT HTML standard

`render_aot_html()` in `implementation/autonomous_remediation/communication_templates.py` is the deterministic renderer.

The shell uses:

- Tahoma 10pt body typography;
- dark gray body text `#4d4d4d`;
- centered responsive table layout with `max-width:630px`;
- top reply instruction `*** Please enter replies above this line ***`;
- centered Atlantic Office Technologies logo at 150px width;
- light gray outer/notification background `#e5e5e5`;
- white content panel with `1px solid #cccccc` border;
- uppercase 20px bold title;
- muted gray footer `#999999`.

The model does not emit HTML. It emits bounded content slots which are escaped and inserted by the deterministic renderer.

## AI proposal contract

Prompt `PROMPT-COMM-001` v1.0.0 (`AOT Communication Template Proposal`) returns:

- proposed template name;
- reusable subject;
- title;
- intro;
- body paragraphs;
- optional bullet list;
- closing;
- required variables;
- rationale.

The prompt has no provider tools and no send/publish authority. It must not invent client facts, SLA/pricing/legal language, security conclusions, or actions already taken. Ticket-specific values belong in named variables rather than hard-coded reusable text.

## Audience and send governance

Template approval does not itself authorize sending. Client/company/contact binding, audience policy, communication channel authority, preview/approval policy, and post-send evidence remain separately governed.

A proposed/unapproved template must never be used as an implicitly approved client response.

## Observability

Dashboard UID: `jason-communication-templates`.

Exporter port: 9473.

Metrics expose approved-template count, request count, open requests, lifecycle, audience, proposed template name/subject, and recurrence. HTML bodies, ticket IDs, run IDs, and communication content are intentionally excluded from Prometheus.

## Current provider gap

`TODO-COMM-005` remains open for authoritative template-content population/use and governed dispatch. `TODO-COMM-006` remains the minimum Notification History permission change needed for post-send/template-name evidence. The Jason catalog/request workflow does not bypass those provider limitations.
