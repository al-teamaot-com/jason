#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/cap-001/src:/home/al/projects/jason/implementation/cap-002/src:/home/al/projects/jason/implementation/cap-003/src:/home/al/projects/jason/implementation/cap-007/src:/home/al/projects/jason/implementation/cli/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/runtime_service/src"

echo "========== START LIVE SITE OUTCOME CONTRACT PROOF =========="

echo "========== SECTION 1: REPOSITORY STATE =========="
git status --short
git log -1 --oneline --decorate

echo "========== SECTION 2: WORKTREE INTERPRETER + PLANNER PROOF =========="
./.venv-test/bin/python - <<'PY'
from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from orchestrator.conversation_resource_intent import MetadataFirstResourceInquiryInterpreter
from orchestrator.resource_capability_catalog import register_endpoint_resource_foundation
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner


class NoFallback:
    def interpret(self, **kwargs):
        raise AssertionError("deterministic proof unexpectedly required fallback")


capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
register_endpoint_resource_foundation(
    capabilities=capabilities,
    providers=providers,
    now=datetime(2026, 8, 12, tzinfo=timezone.utc),
)

contracts = []
for capability in capabilities.list_all():
    metadata = capability.metadata
    if metadata.get("provider_neutral", "false").lower() != "true":
        continue
    if metadata.get("read_only", "false").lower() != "true":
        continue
    resource_types = tuple(x.strip() for x in metadata.get("resource_types", "").split(",") if x.strip())
    contracts.append({
        "capability_name": capability.capability_name,
        "resource_types": resource_types,
        "selector_keys": tuple(x.strip() for x in metadata.get("selector_keys", "").split(",") if x.strip()),
        "fact_hints": tuple(x.strip() for x in metadata.get("fact_hints", "").split(",") if x.strip()),
        "collection_fact": metadata.get("collection_fact", "").strip(),
        "selector_required": any(x in resource_types for x in ("endpoint", "endpoint_alert", "endpoint_audit", "endpoint_software")),
    })

interpreter = MetadataFirstResourceInquiryInterpreter(
    contracts=tuple(contracts),
    fallback=NoFallback(),
)
planner = GovernedResourceInquiryPlanner(
    registry=capabilities,
    reasoner=MetadataResourceCapabilityReasoner(),
)

for text in (
    "List every site in Datto RMM",
    "Please list the sites in Datto RMM",
    "How many sites are in Datto RMM?",
):
    inquiry = interpreter._interpret_deterministically(text)
    print("INPUT:", text)
    print("INQUIRY:", inquiry)
    assert inquiry is not None
    plan = planner.plan(inquiry)
    print("PLAN:", plan.steps[0].capability_name, dict(plan.steps[0].arguments))
    print()

first = interpreter._interpret_deterministically("List every site in Datto RMM")
assert first is not None
assert first.requested_facts == ("sites",)
assert first.result_intent == "enumerate"
assert first.completeness_requirement == "complete"
first_plan = planner.plan(first)
assert first_plan.steps[0].arguments["requested_facts"] == ("sites",)
assert first_plan.steps[0].arguments["result_intent"] == "enumerate"
assert first_plan.steps[0].arguments["completeness_requirement"] == "complete"
print("WORKTREE OUTCOME CONTRACT: PASS")
PY

echo "========== SECTION 3: DEPLOYED CONTAINER SOURCE CHECK =========="
docker exec jason-runtime python - <<'PY'
import inspect
import orchestrator.conversation_resource_intent as cri
import orchestrator.resource_reasoner as rr
import jason_runtime.composition as comp

print('INTERPRETER FILE:', inspect.getfile(cri.MetadataFirstResourceInquiryInterpreter))
print('HAS COLLECTION NORMALIZATION:', 'collection_fact' in inspect.getsource(cri.MetadataFirstResourceInquiryInterpreter._interpret_deterministically))
print('COMPOSITION HAS COLLECTION FACT:', 'collection_fact' in inspect.getsource(comp._deterministic_resource_contracts))
source = inspect.getsource(rr.MetadataResourceCapabilityReasoner.select)
print('PLANNER PROPAGATES RESULT INTENT:', 'result_intent' in source)
print('PLANNER PROPAGATES COMPLETENESS:', 'completeness_requirement' in source)
PY

echo "========== SECTION 4: DEPLOYED IMAGE/CONTAINER =========="
docker inspect jason-runtime --format 'Image={{.Image}} Created={{.Created}} Status={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
docker image inspect jason-runtime:local --format 'LocalImage={{.Id}} Created={{.Created}}'

echo "========== END LIVE SITE OUTCOME CONTRACT PROOF =========="
