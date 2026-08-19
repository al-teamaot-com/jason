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