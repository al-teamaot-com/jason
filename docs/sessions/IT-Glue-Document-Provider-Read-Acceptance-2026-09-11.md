# IT Glue Document Provider-Read Acceptance - 2026-09-11

## Outcome

Bounded provider-backed acceptance passed for the governed IT Glue document read foundation.

Accepted canonical capabilities:

- `documentation.document.search`
- `documentation.document.read`

Both capabilities remain source-default **PILOT**. This acceptance does not activate them in production.

## Defect discovered by live acceptance

The original source mapped document collection search to:

`GET /documents`

The live provider returned the bounded safe failure:

`PROVIDER_HTTP_STATUS_404`

OpenBao health and credential access had already passed, and governed IT Glue organization reads were operational. The failure therefore identified an incorrect provider route rather than a credential, OpenBao, authority, or transport failure.

The corrected collection route is:

`GET /organizations/:organization_id/relationships/documents`

Exact document reads remain:

`GET /documents/:document_id`

The canonical adapter now requires organization scope for document collection searches and no longer advertises unsupported global/name document collection selectors.

## Accepted source

Pre-correction source commit:

`8a49d1628fc14df1b4cc22fadde1f39bb78ea483`

Corrected source commit:

`70cf5db161118d5066fd0c4882bf965da54f460d`

Accepted source patch SHA-256:

`28036d5af3a88384da27b83facb70ea9e8130d0efaa0a2322a7e56d72b7db5cb`

## Provider-backed proof

Live acceptance on 2026-09-11 produced:

- bounded organization sample: 25
- organizations checked before a document candidate was found: 2
- successful organization-scoped document searches: 2
- maximum documents returned per search: 1
- `documentation.document.search`: **PASS**
- `documentation.document.read`: **PASS**
- provider backed: **YES**
- provider mutation: **NO**
- provider identifiers printed: **NO**
- provider identifiers persisted: **NO**
- raw provider payload printed: **NO**
- raw provider payload persisted: **NO**
- credential values exposed: **NO**
- hosted model used: **NO**
- Jason-side hosted model cost: **0**
- durable activation changed: **NO**
- MCP document capability activation changed: **NO**
- production services restarted: **NO**

Sanitized external evidence SHA-256:

`f97a12efeabe1341b5d494496d906e6602977e7506a52531dc995ed2cb68efcf`

The sanitized evidence remains outside the repository.

## Regression proof

After the provider-route correction:

- focused document regression suite: **PASS**
- full scoped governed provider-read regression suite: **PASS**
- source diff validation: **PASS**

The broader scoped suite completed with all selected tests passing.

## Governance boundary

Acceptance used:

- the existing IT Glue read-only AppRole bootstrap;
- the OpenBao logical-secret boundary;
- Central Orchestrator;
- deterministic execution;
- observe-mode provider reads;
- zero hosted-model budget.

IT Glue password and credential-vault data remain outside the admitted read surface.

## Activation state

This provider-backed proof does **not** authorize or perform:

- production deployment;
- production service restart;
- production MCP activation of document capabilities;
- new authority grants;
- provider writes;
- provider-specific MCP tools;
- merge of PR #171.

A separate explicit production activation decision remains required.
