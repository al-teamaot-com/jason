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
echo "It derives an already-active production Microsoft identity binding read-only."
echo "It prints only requested endpoint fact values; identity IDs and secrets are not printed."

echo "========== SECTION 2: LIVE GOVERNED REQUESTS =========="
PYTHONPATH="implementation:implementation/runtime_service/src:implementation/cap-007/src:implementation/connectors/openclaw/src" .venv/bin/python - <<'PY'
from __future__ import annotations

import os
import sqlite3

from jason_runtime.composition import RuntimeSettings, build_runtime_application
from orchestrator.teams_conversation_flow import TeamsConversationPrincipalEvidence


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

# Prefer explicitly supplied values when present. Otherwise derive the already-bound
# production identity for person-al from the durable binding database. This is a
# read-only proof convenience; it creates or modifies no identity/authority state.
tenant_id = os.environ.get("JASON_PROOF_MICROSOFT_TENANT_ID")
object_id = os.environ.get("JASON_PROOF_MICROSOFT_OBJECT_ID")
if not (tenant_id and object_id):
    uri = f"file:{settings.bindings_db}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            """
            SELECT microsoft_tenant_id, microsoft_object_id
            FROM microsoft_identity_bindings
            WHERE jason_identity_id = ? AND status = 'active'
            ORDER BY microsoft_tenant_id, microsoft_object_id
            """,
            ("person-al",),
        ).fetchall()
    except sqlite3.Error as exc:
        raise SystemExit(f"ERROR: could not read production identity bindings: {exc}") from exc
    finally:
        try:
            connection.close()
        except Exception:
            pass

    if len(rows) != 1:
        raise SystemExit(
            "ERROR: expected exactly one active production Microsoft binding for person-al; "
            f"found {len(rows)}. No identity was selected."
        )
    tenant_id, object_id = (str(rows[0][0]), str(rows[0][1]))
    print("IDENTITY_SOURCE: existing active production binding for person-al")
else:
    print("IDENTITY_SOURCE: explicit proof environment variables")

identity = TeamsConversationPrincipalEvidence(
    microsoft_tenant_id=str(tenant_id),
    microsoft_object_id=str(object_id),
    authentication_assurance="botframework-authenticated",
    conversation_id="canonical-fact-proof",
    message_id="canonical-fact-proof",
)

principal = binder.bind(identity)
if principal is None:
    raise SystemExit("ERROR: derived/supplied proof identity is not bound to an active Jason principal")
print("PRINCIPAL_BINDING: PASS")

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
    print("FACT_NORMALIZATION: PASS")
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