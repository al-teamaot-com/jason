#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/cap-001/src:/home/al/projects/jason/implementation/cap-002/src:/home/al/projects/jason/implementation/cap-003/src:/home/al/projects/jason/implementation/cap-007/src:/home/al/projects/jason/implementation/cli/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/runtime_service/src"

echo "========== START LIVE SITE OUTCOME CONTRACT PROOF =========="

echo "========== SECTION 1: REPOSITORY STATE =========="
git status --short
git log -1 --oneline --decorate

echo "========== SECTION 2: WORKTREE INTERPRETER PROOF =========="
./.venv-test/bin/python - <<'PY'
from pathlib import Path
from jason_runtime.composition import RuntimeSettings, build_runtime_application

settings = RuntimeSettings(
    authority_db=Path('/tmp/jason-site-proof-authority.sqlite3'),
    bindings_db=Path('/tmp/jason-site-proof-bindings.sqlite3'),
    replay_db=Path('/tmp/jason-site-proof-replay.sqlite3'),
    security_audit_db=Path('/tmp/jason-site-proof-security.sqlite3'),
    orchestration_events_db=Path('/tmp/jason-site-proof-events.sqlite3'),
    trusted_keys_registry=Path('/tmp/jason-site-proof-keys.json'),
    openbao_url='http://openbao:8200',
    openbao_role_id_path=Path('/tmp/unused-role'),
    openbao_secret_id_path=Path('/tmp/unused-secret'),
    ollama_url='http://jason-ollama:11434',
    ollama_model='proof',
    allowed_machine_identities=frozenset({'svc-openclaw-gateway'}),
)
app = build_runtime_application(settings)
resolver = app.ingress.ingress.flow.intent_resolver.resolvers[0]
interpreter = resolver.interpreter

for text in (
    'List every site in Datto RMM',
    'Please list the sites in Datto RMM',
    'How many sites are in Datto RMM?',
):
    inquiry = interpreter._interpret_deterministically(text)
    print('INPUT:', text)
    print('INQUIRY:', inquiry)
    if inquiry is not None:
        plan = resolver.planner.plan(inquiry)
        print('PLAN:', plan.steps[0].capability_name, dict(plan.steps[0].arguments))
    print()
PY

echo "========== SECTION 3: DEPLOYED CONTAINER SOURCE CHECK =========="
docker exec jason-runtime python - <<'PY'
import inspect
import orchestrator.conversation_resource_intent as cri
import jason_runtime.composition as comp

print('INTERPRETER FILE:', inspect.getfile(cri.MetadataFirstResourceInquiryInterpreter))
print('HAS COLLECTION NORMALIZATION:', 'collection_fact' in inspect.getsource(cri.MetadataFirstResourceInquiryInterpreter._interpret_deterministically))
print('COMPOSITION HAS COLLECTION FACT:', 'collection_fact' in inspect.getsource(comp._deterministic_resource_contracts))
PY

echo "========== SECTION 4: DEPLOYED IMAGE/CONTAINER =========="
docker inspect jason-runtime --format 'Image={{.Image}} Created={{.Created}} Status={{.State.Status}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
docker image inspect jason-runtime:local --format 'LocalImage={{.Id}} Created={{.Created}}'

echo "========== END LIVE SITE OUTCOME CONTRACT PROOF =========="
