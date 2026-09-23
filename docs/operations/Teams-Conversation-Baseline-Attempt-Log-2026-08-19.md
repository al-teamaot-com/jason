# Teams Conversation Baseline Attempt Log

**Date:** 2026-08-19  
**Status:** Active evidence record  
**Parent workstream:** `docs/operations/Teams-Conversation-Working-Baseline-2026-08-18.md`

## Purpose

Record baseline attempts separately from application changes so deployment-tooling failures are not mistaken for Jason conversation failures and failed approaches are not repeated.

## Attempt 1 — Build/export failure before runtime startup

- **Hypothesis:** disabling dynamic conversation through the operator helper would isolate the existing conversation path for live testing.
- **Change:** invoked `jason-ops.sh baseline-deploy` after pulling commit `80a938e`.
- **Observed result:** Compose validation passed, but Docker failed while exporting/importing the rebuilt `jason-runtime:local` image with `unexpected digest ... copied`.
- **Failure class:** local Docker/BuildKit image export/import failure before Jason runtime startup.
- **Application conclusion:** no conclusion about either conversation path is valid because the candidate runtime never started.
- **Lesson:** deployment failures must be isolated from application failures.
- **Do not repeat:** do not change conversation architecture because an image build/import failed.

## Attempt 2 — Bounded retry repeated the same deterministic build failure

- **Hypothesis:** the image export/import problem might be transient, so one bounded build retry could recover without changing source.
- **Change:** commit `e4b19bc` added one bounded retry to the runtime image build used by the baseline deploy path.
- **Observed result:** both build attempts failed on the same image export/import operation with the same unexpected digest. Baseline mode was never reached.
- **Failure class:** persistent deployment-method failure. Repeating the same build under unchanged conditions did not create a new recovery path.
- **Application conclusion:** again, no Teams conversation behavior was tested.
- **Lesson:** a retry is only useful when the failure class is plausibly transient. Identical deterministic failures should cause the deployment method to change rather than repeat.
- **Do not repeat:** do not rebuild the runtime merely to toggle a runtime environment flag when the existing image already contains both code paths.

## Attempt 3 — Baseline recreation succeeded but reused stale application code

- **Hypothesis:** after pulling the structural semantic-coverage changes, `baseline-deploy` would let the live runtime exercise those changes while preserving the non-dynamic conversation path.
- **Change:** pulled through commit `6a06ae5` and invoked `jason-ops.sh baseline-deploy`.
- **Observed result:** baseline recreation passed and `JASON_DYNAMIC_CONVERSATION_ENABLED=false` was verified, but the live IP-address question returned the exact pre-change `governed_fact_not_available` response.
- **Failure class:** deployment provenance failure. `baseline-deploy` intentionally uses `--no-build`, so it recreated the container from the previously installed `jason-runtime:local` image. Pulling source did not put the new source into that image.
- **Application conclusion:** the live result does not test the structural semantic-coverage code added after the existing image was built.
- **Lesson:** configuration-only baseline transitions and source-code baseline refreshes are two different operations. The former must avoid rebuilding; the latter must produce a new image and prove which source revision that image contains before live conclusions are accepted.
- **Do not repeat:** never treat `git pull` plus `--no-build` container recreation as deployment of new application code.

## Attempt 4 — Timestamp presentation smoke exposed canonical-label resolution gap

- **Hypothesis:** the verified timestamp presentation code was deployed but not reached by the Teams response path.
- **Change:** strengthened `jason-baseline-refresh.sh` to prove the running image ID, source revision, and execute the semantic timestamp presentation function inside the live runtime container.
- **Observed result:** running image and revision both matched the freshly built source, but the in-container smoke test returned the raw numeric timestamp unchanged.
- **Failure class:** semantic contract continuity failure. The semantic registry could resolve human aliases such as `last seen` but could not resolve its own already-canonical label `endpoint last seen` back to the same active concept metadata.
- **Application conclusion:** deployment and Teams routing were not the cause of the raw timestamp presentation at this stage.
- **Lesson:** canonicalization is only safe when canonical labels are stable, round-trippable identifiers throughout downstream semantic processing.
- **Do not repeat:** do not patch the timestamp formatter or add duplicate aliases when an already-canonical semantic label loses its concept metadata downstream.

## Attempt 5 — Live Teams request blocked by upstream throttling before orchestration

- **Hypothesis:** after canonical-label resolution was corrected, a repeated Teams `last seen` request would exercise the verified retrieval and presentation path.
- **Observed result:** Teams returned `Jason could not safely process that request. No action was taken.` The 10-minute capture showed three authenticated conversation attempts failing with `ConnectorTransportError: HTTP transport failed with status 429`. No new orchestration events were created for those attempts.
- **Failure class:** transient upstream identity-enrichment throttling before Central Orchestrator execution, not semantic resolution, capability planning, Datto retrieval, or response rendering.
- **Evidence boundary:** the failure occurs after OpenClaw/Teams authentication but before orchestration. The legacy composition performs governed Microsoft directory enrichment during identity binding in that interval, making Microsoft Graph directory read the bounded external dependency implicated by the observed 429.
- **Application conclusion:** the live 429 result cannot be used to judge the canonical-label or timestamp-presentation fix because no governed resource orchestration occurred.
- **Lesson:** authenticated conversational ingress must distinguish transient provider throttling from semantic/application failures, preserve safe provider retry metadata, and retry only within an explicit bounded policy.
- **Do not repeat:** do not change semantic mappings, capability routing, Datto code, or presentation logic in response to a pre-orchestration HTTP 429.

## Attempt 6 — Retry policy exposed a deeper authority/enrichment coupling defect

- **Hypothesis:** bounded Microsoft Graph retry would allow transient 429 throttling to clear without changing the authenticated Teams identity model.
- **Observed result:** after deploying the bounded 429 retry, a new Teams turn still authenticated successfully and failed before orchestration with `ConnectorTransportError: HTTP transport failed with status 429`. The turn lasted only a few seconds and again created no new orchestration events.
- **Failure class:** authority-boundary coupling defect. A mutable profile enrichment read (`mail`/`userPrincipalName`) was being treated as a mandatory prerequisite for a principal whose authoritative tenant/object binding and Jason identity record had already been verified.
- **Violated invariant:** non-authoritative enrichment must not invalidate an already authenticated and Jason-bound principal when the enrichment provider is unavailable or throttled.
- **General correction:** keep the authoritative identity path as authenticated Teams tenant/object evidence -> active Microsoft binding -> active Jason identity. Directory email remains optional live enrichment. Transport failure omits the mutable email attribute for that turn rather than substituting stale profile data or rejecting the verified principal. Semantic/authorization failures from the directory itself remain fail-closed.
- **Application conclusion:** the repeated 429 still says nothing about Datto retrieval or timestamp rendering. It instead revealed that profile enrichment was positioned too high in the authority path.
- **Lesson:** external profile freshness and identity authority are separate contracts. A provider-neutral principal must be able to exist without mutable enrichment fields unless a later capability explicitly requires them.
- **Do not repeat:** do not make ordinary Teams reads depend synchronously on external mutable-profile enrichment when that enrichment is not an authority input for the requested operation.

## Attempt 7 — Live provenance proved the remaining 429 came from optional hosted semantics

- **Hypothesis:** the post-authentication 429 was still escaping the Microsoft identity binder.
- **Observed result:** the live runtime revision was confirmed as `08beb26`; `JASON_DYNAMIC_CONVERSATION_ENABLED=false`; `JASON_HOSTED_SEMANTICS_ENABLED=true`; and an in-container synthetic Microsoft directory 429 produced `IDENTITY_BINDER_SMOKE=PASS` with the email omitted. The real Teams turn still failed before orchestration with HTTP 429 and no Ollama activity.
- **Failure class:** backend semantic-provider availability was incorrectly coupled to the human-facing conversation path. Hosted semantic translation is interpretation assistance, not identity, authority, evidence, or execution authority, yet its transport failure escaped instead of degrading to the next governed interpretation path.
- **Violated invariant:** Teams conversational availability and quality must not depend on one backend reasoning provider when another governed path can safely interpret the same read request.
- **General correction:** catch only `ConnectorTransportError` from hosted semantic translation and continue to the existing local semantic reasoner or normal governed fallback. Permission, schema, catalog-boundary, and other semantic-contract violations still fail closed and are never converted into fallback success.
- **Application conclusion:** the 429 no longer justifies any identity, Datto, capability, or presentation change. It is a semantic backend availability concern and should remain behind the interface-quality boundary.
- **Lesson:** provider outage and provider semantic violation are different failure classes. Availability failure may degrade to an alternate governed backend; safety/contract failure must not.
- **Do not repeat:** do not make a hosted model/provider a synchronous single point of failure for ordinary governed reads when Jason already has a bounded local interpretation path.

## Baseline Deployment Modes

### Configuration-only baseline transition

When the application image is already known to contain the desired code and the experiment changes only runtime configuration, the baseline transition changes exactly one intended variable: `JASON_DYNAMIC_CONVERSATION_ENABLED=false`.

That transition must:

1. recover the currently mounted credential-file paths and current Ollama model from the existing runtime container;
2. validate those required inputs without printing secret values;
3. confirm the existing `jason-runtime:local` image is present;
4. apply a temporary Compose override containing only `JASON_DYNAMIC_CONVERSATION_ENABLED=false`;
5. validate the combined Compose configuration;
6. recreate only `jason-runtime` using `docker compose up --no-build --no-deps --force-recreate`;
7. wait for runtime health;
8. verify the live container environment reports `JASON_DYNAMIC_CONVERSATION_ENABLED=false`;
9. only then begin Teams baseline questions.

No image build belongs in a configuration-only transition.

### Source-code baseline refresh

When source code has changed, the baseline must first refresh `jason-runtime:local` from the current repository revision and prove image provenance. The refresh path must:

1. capture the current Git revision;
2. preserve the currently installed image under a rollback tag;
3. avoid the custom `jason-builder` BuildKit path that already failed deterministically on image import;
4. build through Docker's default buildx builder;
5. stamp the image with `org.opencontainers.image.revision=<current Git SHA>`;
6. verify that label from the installed image;
7. only then invoke the configuration-only `baseline-deploy` transition;
8. accept live evidence only when image revision and repository revision match.

`infrastructure/jason-runtime/jason-baseline-refresh.sh` implements this source-code refresh path.

## Governing Lesson

> A working-baseline experiment must minimize simultaneous variables, but it must also prove deployment provenance. Configuration-only recreation proves configuration; it does not prove that newly pulled source is running. Any live conclusion about a code change requires a provenance-verified image built from that revision.

> An observed transport failure must remain classified at the layer where it occurred. A pre-orchestration provider throttle is not evidence of a semantic, capability, Datto, or rendering defect.

> Identity authority and mutable profile enrichment are separate contracts. Once authenticated Teams tenant/object evidence has been bound to an active Jason identity, failure of non-authoritative profile enrichment may remove the enrichment but must not invalidate that principal unless the failed provider result itself carries an authority-relevant denial.

> Backend semantic-provider availability is not a user-facing authority boundary. Transport failure may fall through to another governed semantic path; semantic-contract or authorization violations must still fail closed.
