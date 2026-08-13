#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE OBSERVE-ONLY SEMANTIC PLANNER INTENT PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

if ! docker inspect jason-runtime >/dev/null 2>&1; then
  echo "ERROR: running jason-runtime container is required to reach the current local Ollama service."
  exit 21
fi

MODEL="$(docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^JASON_OLLAMA_MODEL=//p' | head -n 1)"
OLLAMA_URL="$(docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^JASON_OLLAMA_URL=//p' | head -n 1)"
if [ -z "$MODEL" ]; then
  echo "ERROR: could not derive JASON_OLLAMA_MODEL from running jason-runtime."
  exit 22
fi
if [ -z "$OLLAMA_URL" ]; then
  OLLAMA_URL="http://jason-ollama:11434"
fi

echo "MODEL=SET"
echo "OLLAMA_URL=SET"

echo "========== SECTION 2: RUN REAL LOCAL-OLLAMA PLANNING LOOP =========="
JASON_PROBE_MODEL="$MODEL" JASON_PROBE_OLLAMA_URL="$OLLAMA_URL" "$PY" - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Mapping

from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.ollama_semantic_intent_planning import OllamaSemanticIntentPlanningReasoner
from orchestrator.planning_context_reader import GovernedPlanningContextReaderAdapter
from orchestrator.planning_context_views import GovernedPlanningContextCatalog, StaticPlanningContextProvider
from orchestrator.resource_capability_catalog import (
    endpoint_alert_search,
    endpoint_audit_read,
    endpoint_device_read,
    endpoint_device_search,
    endpoint_software_search,
    management_alert_search,
    management_site_search,
)
from orchestrator.semantic_intent_planning_loop import BoundedSemanticIntentPlanningLoop, IntentPlanningBudget
from orchestrator.semantic_planning_bootstrap import ProviderNeutralIntentContextBootstrapper
from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry


class DockerExecOllamaTransport:
    """Read-only probe transport into the existing runtime network namespace."""

    def request(self, *, method: str, url: str, headers: Mapping[str, str], json: Mapping[str, Any], timeout_seconds: float):
        del headers
        if method != "POST":
            raise ValueError("probe transport permits POST only")
        payload = {
            "url": url,
            "body": dict(json),
            "timeout": float(timeout_seconds),
        }
        code = r'''
import json, sys, urllib.request
p = json.load(sys.stdin)
body = json.dumps(p["body"]).encode("utf-8")
req = urllib.request.Request(p["url"], data=body, headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=p["timeout"]) as r:
    sys.stdout.write(r.read().decode("utf-8"))
'''
        proc = subprocess.run(
            ["docker", "exec", "-i", "jason-runtime", "python", "-c", code],
            input=json_module_dumps(payload),
            text=True,
            capture_output=True,
            timeout=max(5.0, timeout_seconds + 10.0),
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Ollama probe transport failed: {proc.stderr.strip()[:240]}")
        parsed = json_module_loads(proc.stdout)
        if not isinstance(parsed, Mapping):
            raise ValueError("Ollama probe response must be an object")
        return dict(parsed)


def json_module_dumps(value: Any) -> str:
    return json.dumps(value)


def json_module_loads(value: str) -> Any:
    return json.loads(value)


now = datetime.now(timezone.utc)
capability_defs = (
    endpoint_device_search(now),
    endpoint_device_read(now),
    endpoint_alert_search(now),
    endpoint_audit_read(now),
    endpoint_software_search(now),
    management_alert_search(now),
    management_site_search(now),
)
capability_records = tuple(
    {
        "capability_name": item.capability_name,
        "display_name": item.display_name,
        "business_purpose": item.business_purpose,
        "resource_types": str(item.metadata.get("resource_types", "")),
        "operation": str(item.metadata.get("operation", "")),
        "fact_hints": str(item.metadata.get("fact_hints", "")),
        "planning_guidance": str(item.metadata.get("planning_guidance", "")),
    }
    for item in capability_defs
)

evidence_records = tuple(
    {
        "capability_name": item.capability_name,
        "fact_hints": str(item.metadata.get("fact_hints", "")),
        "evidence_required": bool(item.evidence.required),
        "evidence_requirements": " | ".join(item.evidence.requirements),
        "verification_requirements": " | ".join(item.evidence.verification_requirements),
    }
    for item in capability_defs
)

registry = build_trusted_semantic_registry()
semantic_records = []
seen = set()
for term in registry.active_terms():
    concept = registry.resolve_term(term)
    if concept is None:
        continue
    key = (term.casefold(), concept.concept_id)
    if key in seen:
        continue
    seen.add(key)
    semantic_records.append(
        {
            "term": term,
            "concept_id": concept.concept_id,
            "canonical_name": concept.canonical_label,
        }
    )

relationship_records = tuple(
    {
        "relationship_id": rel.relationship_id,
        "subject_type": rel.subject_type,
        "target_type": rel.target_type,
    }
    for rel in registry.active_relationships()
)

catalog = GovernedPlanningContextCatalog(
    providers={
        "semantic_knowledge": StaticPlanningContextProvider(
            view_name="semantic_knowledge",
            records=tuple(semantic_records),
            searchable_fields=("term", "concept_id", "canonical_name"),
        ),
        "capabilities": StaticPlanningContextProvider(
            view_name="capabilities",
            records=capability_records,
            searchable_fields=("capability_name", "display_name", "business_purpose", "resource_types", "operation", "fact_hints", "planning_guidance"),
        ),
        "system_state": StaticPlanningContextProvider(
            view_name="system_state",
            records=({"service": "jason-runtime", "state": "available"},),
            searchable_fields=("service", "state"),
        ),
        "evidence_catalog": StaticPlanningContextProvider(
            view_name="evidence_catalog",
            records=evidence_records,
            searchable_fields=("capability_name", "fact_hints", "evidence_requirements", "verification_requirements"),
        ),
        "derivations": StaticPlanningContextProvider(
            view_name="derivations",
            records=relationship_records,
            searchable_fields=("relationship_id", "subject_type", "target_type"),
        ),
    }
)

model = os.environ["JASON_PROBE_MODEL"]
base_url = os.environ["JASON_PROBE_OLLAMA_URL"]
client = OllamaStructuredJsonClient(
    transport=DockerExecOllamaTransport(),
    model=model,
    base_url=base_url,
    timeout_seconds=60.0,
)
planner = BoundedSemanticIntentPlanningLoop(
    reasoner=OllamaSemanticIntentPlanningReasoner(client=client),
    context_reader=GovernedPlanningContextReaderAdapter(catalog=catalog, default_limit=48),
    budget=IntentPlanningBudget(max_iterations=8, max_context_requests=7),
    context_bootstrapper=ProviderNeutralIntentContextBootstrapper(),
    plan_validator=GovernedSemanticPlanSufficiencyValidator(),
)

intent = {
    "human_text": "What is the Windows Display Version for AOT-50282?",
    "resource_type": "endpoint",
    "resource_selector": {"hostname": "AOT-50282"},
    "requested_facts": ["operating system display version"],
    "permission_mode": "observe",
    "result_intent": "summary",
    "completeness_requirement": "sufficient",
}

outcome = planner.plan(intent=intent)
print(f"OUTCOME_STATUS={outcome.status}")
print(f"ITERATIONS_USED={outcome.iterations_used}")
print(f"CONTEXT_REQUESTS_USED={outcome.context_requests_used}")
for entry in outcome.trace:
    print(f"TRACE iteration={entry.iteration} status={entry.status} context_view={entry.context_view or '-'}")
if outcome.plan is not None:
    print(f"PLAN_STEP_COUNT={len(outcome.plan.steps)}")
    for index, step in enumerate(outcome.plan.steps, 1):
        print(f"PLAN_STEP[{index}] capability={step.capability_name} purpose={step.purpose}")
        print(f"PLAN_STEP[{index}] required_facts={','.join(step.required_facts) or '-'}")
        print(f"PLAN_STEP[{index}] expected_evidence={','.join(step.expected_evidence) or '-'}")
    print(f"UNRESOLVED_REQUIREMENTS={','.join(outcome.plan.unresolved_requirements) or '-'}")
if outcome.gap_summary:
    print(f"KNOWLEDGE_GAP={outcome.gap_summary}")
PY

echo "========== SECTION 3: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live local-Ollama semantic intent planning probe completed in observe-only mode."
echo "The probe used governed semantic/capability/evidence context and did not execute any proposed capability."
echo "NO PROVIDER READ OR MUTATION WAS PERFORMED BY THE PLANNER."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE OBSERVE-ONLY SEMANTIC PLANNER INTENT PROBE =========="
