# Constant Contact complete workbook intake — 2026-11-25

## Defects and correction

The existing bounded XLSX parser relied on worksheet dimensions supplied by
the file. An underreported range hid an unconsented contact or formula beyond
that range. The initial test fixture's text substitution did not change the
XML because of whitespace before the closing tag; the regression fixtures now
explicitly assert the transformation changed the original package member.
Both actual defects then reproduced before the source correction.

Inspect the actual read-only worksheet stream instead of trusting dimensions
to truncate it. Enforce the existing declared and actual row/column bounds,
reject trailing columns without approved headers, and preserve formula,
duplicate, consent, single-sheet, decompression and original-byte hash
controls.

External relationships were also detected using exact XML byte strings.
Whitespace around the assignment or alternative XML encoding could bypass
that check. Parse bounded relationship XML with the standard-library Expat
parser, reject external or unknown target modes, malformed XML and DTD/entity
declarations. No external resource is loaded.

## Verification

31 focused XLSX/handoff tests passed, including the reproduced defects, XML
whitespace, character references, UTF-16, external and unknown modes, DTDs,
malformed XML, actual row/column limits, and unapproved columns. All 234
Constant Contact connector, MCP handoff, orchestrator, runtime, scheduler and
credential-projection regression tests passed in an isolated development
environment. No actual provider calls or consent authority were granted.

The older initial parser draft #2352 must not be merged as a parallel intake
path. Current integration uses the stricter shared xlsx_preflight and
intake_handoff path with explicit consent and original attachment evidence.
This correction does not introduce the older draft's alternative header
aliases or worksheet selection, and does not claim these optional features
were accepted.

## Release boundary

The separate previously merged OAuth client-identification correction #2472
was rehearsed in an isolated copy of the running MCP image, adding only the
exact reviewed token-exchange file. Network-disabled synthetic tests
reproduced baseline edge rejection and verified the corrected authorization
code and refresh request behavior, including rejection of missing scopes and
missing rotated tokens. Image ancestry and unchanged inherited configuration
were verified; all protected production container identities and start times
were unchanged. The rehearsal image is explicitly not release eligible.

The historical pinned OAuth release remains blocked by current
protected-ancestry controls. This source correction neither relaxes those
controls nor authorizes replacement of the running MCP. A newly reviewed
native release scope, exact approval, actual OAuth consent and provider
readback/import acceptance remain required. No contacts, provider credentials,
live OAuth state or production services changed during these tests.
