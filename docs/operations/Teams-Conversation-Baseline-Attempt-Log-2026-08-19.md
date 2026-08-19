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

## Corrected Baseline Deployment Method

The baseline test changes exactly one intended variable: `JASON_DYNAMIC_CONVERSATION_ENABLED=false`.

The existing installed `jason-runtime:local` image already contains both the legacy and dynamic conversation implementations. Therefore the baseline deployment must:

1. recover the currently mounted credential-file paths and current Ollama model from the existing runtime container;
2. validate those required inputs without printing secret values;
3. confirm the existing `jason-runtime:local` image is present;
4. apply a temporary Compose override containing only `JASON_DYNAMIC_CONVERSATION_ENABLED=false`;
5. validate the combined Compose configuration;
6. recreate only `jason-runtime` using `docker compose up --no-build --no-deps --force-recreate`;
7. wait for runtime health;
8. verify the live container environment reports `JASON_DYNAMIC_CONVERSATION_ENABLED=false`;
9. only then begin Teams baseline questions.

No Docker image build, BuildKit export/import, cache pruning, source modification, provider change, or conversation-code change belongs in this baseline transition.

## Governing Lesson

> A working-baseline experiment must minimize simultaneous variables. If the desired experiment is a runtime configuration change and the existing image already contains both paths, rebuilding the image is an unrelated variable and should be excluded.
