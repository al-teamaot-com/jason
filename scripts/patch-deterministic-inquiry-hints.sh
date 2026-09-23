#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

echo "========== START DETERMINISTIC INQUIRY HINT SEPARATION =========="

echo "========== SECTION 1: PATCH CAPABILITY METADATA CONTRACT =========="
python3 - <<'PY'
from pathlib import Path

p = Path('implementation/orchestrator/resource_capability_catalog.py')
s = p.read_text(encoding='utf-8')

old = '''    fact_hints: str,
    planning_guidance: str,
    collection_fact: str | None = None,
) -> CapabilityDefinition:
'''
new = '''    fact_hints: str,
    planning_guidance: str,
    collection_fact: str | None = None,
    inquiry_hints: str | None = None,
) -> CapabilityDefinition:
'''
if old in s:
    s = s.replace(old, new, 1)
elif 'inquiry_hints: str | None = None' not in s:
    raise SystemExit('ERROR: capability helper signature anchor not found')

old = '''            "fact_hints": fact_hints,
            **({"collection_fact": collection_fact} if collection_fact else {}),
            "planning_guidance": planning_guidance,
'''
new = '''            "fact_hints": fact_hints,
            "inquiry_hints": inquiry_hints or fact_hints,
            **({"collection_fact": collection_fact} if collection_fact else {}),
            "planning_guidance": planning_guidance,
'''
if old in s:
    s = s.replace(old, new, 1)
elif '"inquiry_hints": inquiry_hints or fact_hints' not in s:
    raise SystemExit('ERROR: capability metadata anchor not found')

old = '''        collection_fact="alerts",
    )


def management_site_search'''
new = '''        collection_fact="alerts",
        inquiry_hints=(
            "alert,alerts,open alert,open alerts,monitoring alert,monitoring alerts,"
            "severity,priority,status,message"
        ),
    )


def management_site_search'''
if old in s:
    s = s.replace(old, new, 1)
elif 'monitoring alerts,"\n            "severity,priority,status,message"' not in s:
    raise SystemExit('ERROR: management alert anchor not found')

old = '''        collection_fact="sites",
    )


def datto_rmm_endpoint_provider'''
new = '''        collection_fact="sites",
        inquiry_hints=(
            "site,sites,client site,managed site,site name,site identifier,site details"
        ),
    )


def datto_rmm_endpoint_provider'''
if old in s:
    s = s.replace(old, new, 1)
elif 'collection_fact="sites",\n        inquiry_hints=' not in s:
    raise SystemExit('ERROR: management site anchor not found')

p.write_text(s, encoding='utf-8')
print('Updated:', p)
PY

echo "========== SECTION 2: USE INQUIRY HINTS FOR DETERMINISTIC RECOGNITION =========="
python3 - <<'PY'
from pathlib import Path

p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')
old = '''        fact_hints = tuple(
            item.strip()
            for item in metadata.get("fact_hints", "").split(",")
            if item.strip()
        )
        collection_fact = metadata.get("collection_fact", "").strip()
'''
new = '''        fact_hints = tuple(
            item.strip()
            for item in metadata.get(
                "inquiry_hints",
                metadata.get("fact_hints", ""),
            ).split(",")
            if item.strip()
        )
        collection_fact = metadata.get("collection_fact", "").strip()
'''
if old in s:
    s = s.replace(old, new, 1)
elif 'metadata.get(\n                "inquiry_hints"' not in s:
    raise SystemExit('ERROR: deterministic contract fact_hints anchor not found')
p.write_text(s, encoding='utf-8')
print('Updated:', p)
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_conversation_resource_intent.py <<'PYTEST'


def test_deterministic_inquiry_hints_separate_resource_identity_from_incidental_facts():
    class ForbiddenFallback:
        def interpret(self, **kwargs):
            raise AssertionError("fallback must not be called")

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.alert.search",
                "resource_types": ("alert",),
                "selector_keys": ("site", "site_id", "status", "severity", "priority"),
                "fact_hints": (
                    "alert",
                    "alerts",
                    "open alert",
                    "open alerts",
                    "severity",
                    "priority",
                    "status",
                    "message",
                ),
                "collection_fact": "alerts",
                "selector_required": False,
            },
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": (
                    "site",
                    "sites",
                    "client site",
                    "managed site",
                    "site name",
                    "site identifier",
                    "site details",
                ),
                "collection_fact": "sites",
                "selector_required": False,
            },
        ),
        fallback=ForbiddenFallback(),
    )

    inquiry = interpreter.interpret(
        text="List every site in Datto RMM",
        principal=principal(),
    )

    assert inquiry is not None
    assert inquiry.resource_type == "management_site"
    assert inquiry.requested_facts == ("sites",)
    assert inquiry.result_intent == "enumerate"
    assert inquiry.completeness_requirement == "complete"
PYTEST

cat >> implementation/orchestrator/tests/test_resource_capability_catalog.py <<'PYTEST'


def test_management_resource_inquiry_hints_do_not_cross_match_incidental_site_fields():
    from orchestrator.resource_capability_catalog import (
        management_alert_search,
        management_site_search,
    )

    alerts = management_alert_search(NOW)
    sites = management_site_search(NOW)

    assert "site" in sites.metadata["inquiry_hints"].split(",")
    assert "site" not in alerts.metadata["inquiry_hints"].split(",")
    assert "site" in alerts.metadata["fact_hints"].split(",")
PYTEST

echo "========== SECTION 4: VALIDATE =========="
export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/cap-001/src:/home/al/projects/jason/implementation/cap-002/src:/home/al/projects/jason/implementation/cap-003/src:/home/al/projects/jason/implementation/cap-007/src:/home/al/projects/jason/implementation/cli/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/runtime_service/src"

git diff --check
./.venv-test/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== RESULT =========="
echo "Deterministic inquiry hint separation validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END DETERMINISTIC INQUIRY HINT SEPARATION =========="
