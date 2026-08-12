#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE CANONICAL ENDPOINT FACT PROOF =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before live proof."
  printf '%s\n' "$DIRTY"
  exit 20
fi
if [[ -f FETCH_HEAD ]]; then
  echo "NOTE: ignoring untracked repository-root FETCH_HEAD artifact; .git/FETCH_HEAD remains authoritative git metadata."
fi

echo "HEAD: $(git rev-parse --short HEAD)"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: .venv/bin/python is required for the production runtime proof."
  exit 21
fi

TARGET="AOT-50282"
export TARGET

echo "TARGET: ${TARGET}"
echo "This proof uses the production runtime composition and governed Datto connector."
echo "It prints only requested endpoint fact values and structural evidence pointers."
echo "It does not print credentials, tokens, or secret material."

echo "========== SECTION 2: LIVE GOVERNED REQUESTS =========="
PYTHONPATH="implementation:implementation/runtime_service/src:implementation/cap-007/src:implementation/connectors/openclaw/src" .venv/bin/python - <<'PY'
from __future__ import annotations

import os

from jason_runtime.composition import RuntimeSettings, build_runtime_application


target = os.environ["TARGET"]
settings = RuntimeSettings.from_env()
app = build_runtime_application(settings)

ingress = app.ingress
outer = getattr(ingress, "ingress", None)
flow = getattr(outer, "flow", None)
if flow is None:
    raise SystemExit("ERROR: production flow could not be located from runtime composition")

binder = flow.identity_binder
resolver = flow.intent_resolver
orchestrator = flow.orchestrator
renderer = flow.response_renderer

identity = None
tenant_id = os.environ.get("JASON_PROOF_MICROSOFT_TENANT_ID")
object_id = os.environ.get("JASON_PROOF_MICROSOFT_OBJECT_ID")
if tenant_id and object_id:
    from orchestrator.teams_identity import TeamsConversationPrincipalEvidence
    identity = TeamsConversationPrincipalEvidence(
        microsoft_tenant_id=tenant_id,
        microsoft_object_id=object_id,
        authentication_assurance="botframework-authenticated",
        conversation_id="canonical-fact-proof",
        message_id="canonical-fact-proof",
    )

if identity is None:
    print("SKIP_LIVE_EXECUTION: production proof identity env vars are not set.")
    print("Set JASON_PROOF_MICROSOFT_TENANT_ID and JASON_PROOF_MICROSOFT_OBJECT_ID to an existing bound production identity and rerun.")
    raise SystemExit(31)

principal = binder.bind(identity)
if principal is None:
    raise SystemExit("ERROR: supplied proof identity is not bound to a Jason principal")

queries = (
    ("processor model", f"What processor is on {target}?"),
    ("total memory", f"How much RAM is in {target}?"),
    ("operating system display version", f"What is the Windows Display Version for {target}?"),
)

for expected_fact, text in queries:
    print(f"--- QUERY: {text}")
    intent = resolver.resolve(text=text, principal=principal)
    if intent is None:
        print("RESOLUTION: NONE")
        continue
    requested = tuple(str(x) for x in intent.arguments.get("requested_facts", ()))
    print("CAPABILITY:", intent.capability_name)
    print("REQUESTED_FACTS:", requested)
    if expected_fact not in requested:
        print("FACT_NORMALIZATION: FAIL expected", expected_fact)
        continue
    request = flow.request_factory.build(principal=principal, intent=intent, identity=identity)
    result = orchestrator.orchestrate(request)
    print("ORCHESTRATION_STATUS:", result.status.value)
    print("PROVIDER:", result.provider_id)
    try:
        text_out = renderer.render(result, intent)
        print("RENDERED:", text_out)
    except Exception as exc:
        print("RENDER_ERROR:", type(exc).__name__, str(exc))
    print()
PY

echo "========== RESULT =========="
echo "Live canonical endpoint fact proof completed."
echo "NO SOURCE CHANGES PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE CANONICAL ENDPOINT FACT PROOF =========="
