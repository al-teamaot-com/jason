#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== START GOVERNED PLANNING CONTEXT VIEWS =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"
git status --short

ALLOWED='^(\?\? FETCH_HEAD)?$'
DIRTY="$(git status --short | grep -v '^?? FETCH_HEAD$' || true)"
if [ -n "$DIRTY" ]; then
  echo "ERROR: unexpected local changes present:"
  printf '%s\n' "$DIRTY"
  exit 21
fi

echo "========== SECTION 2: ADD GOVERNED CONTEXT VIEW CONTRACT =========="
"$PY" - <<'PY'
from pathlib import Path

root = Path('/home/al/projects/jason')
module = root / 'implementation/orchestrator/planning_context_views.py'
tests = root / 'implementation/orchestrator/tests/test_planning_context_views.py'

module.write_text('''from __future__ import annotations\n\nfrom dataclasses import dataclass, field\nfrom typing import Any, Mapping, Protocol, Sequence\n\n\nclass PlanningContextViewUnavailableError(LookupError):\n    \"\"\"A requested governed planning view is unavailable.\"\"\"\n\n\n@dataclass(frozen=True, slots=True)\nclass PlanningContextRequest:\n    view_name: str\n    query: str = \"\"\n    limit: int = 32\n\n    def __post_init__(self) -> None:\n        if not self.view_name.strip():\n            raise ValueError(\"planning context view_name is required\")\n        if self.limit < 1 or self.limit > 128:\n            raise ValueError(\"planning context limit is invalid\")\n\n\n@dataclass(frozen=True, slots=True)\nclass PlanningContextView:\n    view_name: str\n    items: tuple[Mapping[str, Any], ...]\n    authoritative: bool = True\n    truncated: bool = False\n    metadata: Mapping[str, Any] = field(default_factory=dict)\n\n\nclass PlanningContextProvider(Protocol):\n    def read(self, request: PlanningContextRequest) -> PlanningContextView: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass GovernedPlanningContextCatalog:\n    \"\"\"Expose bounded, provider-neutral planning context to a reasoner.\n\n    The catalog never invokes providers, tools, connectors, agents, or credentials.\n    It only returns deterministic views over already-governed Jason registries/state.\n    \"\"\"\n\n    providers: Mapping[str, PlanningContextProvider]\n    allowed_views: tuple[str, ...] = (\n        \"semantic_knowledge\",\n        \"capabilities\",\n        \"system_state\",\n        \"evidence_catalog\",\n        \"derivations\",\n    )\n\n    def read(self, request: PlanningContextRequest) -> PlanningContextView:\n        view_name = request.view_name.strip()\n        if view_name not in self.allowed_views:\n            raise PermissionError(\"planning context view is not allowed\")\n        provider = self.providers.get(view_name)\n        if provider is None:\n            raise PlanningContextViewUnavailableError(\n                f\"planning context view unavailable: {view_name}\"\n            )\n        view = provider.read(request)\n        if view.view_name != view_name:\n            raise RuntimeError(\"planning context provider changed requested view name\")\n        if len(view.items) > request.limit:\n            raise RuntimeError(\"planning context provider exceeded requested limit\")\n        return view\n\n\n@dataclass(frozen=True, slots=True)\nclass StaticPlanningContextProvider:\n    \"\"\"Deterministic test/bootstrap view over already-governed records.\"\"\"\n\n    view_name: str\n    records: Sequence[Mapping[str, Any]]\n    searchable_fields: tuple[str, ...] = ()\n\n    def read(self, request: PlanningContextRequest) -> PlanningContextView:\n        query = request.query.strip().casefold()\n        matched = []\n        for record in self.records:\n            if query:\n                values = []\n                fields = self.searchable_fields or tuple(record.keys())\n                for field in fields:\n                    value = record.get(field)\n                    if value is not None:\n                        values.append(str(value).casefold())\n                if not any(query in value for value in values):\n                    continue\n            matched.append(dict(record))\n            if len(matched) >= request.limit:\n                break\n        return PlanningContextView(\n            view_name=self.view_name,\n            items=tuple(matched),\n            authoritative=True,\n            truncated=len(matched) >= request.limit and len(self.records) > len(matched),\n        )\n''', encoding='utf-8')

tests.write_text('''import pytest\n\nfrom orchestrator.planning_context_views import (\n    GovernedPlanningContextCatalog,\n    PlanningContextRequest,\n    PlanningContextView,\n    PlanningContextViewUnavailableError,\n    StaticPlanningContextProvider,\n)\n\n\ndef test_catalog_allows_only_governed_view_names():\n    catalog = GovernedPlanningContextCatalog(providers={})\n    with pytest.raises(PermissionError):\n        catalog.read(PlanningContextRequest(view_name=\"provider_api\"))\n\n\ndef test_catalog_fails_closed_when_governed_view_is_unavailable():\n    catalog = GovernedPlanningContextCatalog(providers={})\n    with pytest.raises(PlanningContextViewUnavailableError):\n        catalog.read(PlanningContextRequest(view_name=\"capabilities\"))\n\n\ndef test_static_context_provider_returns_bounded_provider_neutral_records():\n    provider = StaticPlanningContextProvider(\n        view_name=\"capabilities\",\n        records=(\n            {\"capability_name\": \"endpoint.device.search\", \"purpose\": \"search endpoints\"},\n            {\"capability_name\": \"ticket.search\", \"purpose\": \"search tickets\"},\n        ),\n        searchable_fields=(\"capability_name\", \"purpose\"),\n    )\n    catalog = GovernedPlanningContextCatalog(providers={\"capabilities\": provider})\n    view = catalog.read(\n        PlanningContextRequest(view_name=\"capabilities\", query=\"endpoint\", limit=1)\n    )\n    assert view.view_name == \"capabilities\"\n    assert len(view.items) == 1\n    assert view.items[0][\"capability_name\"] == \"endpoint.device.search\"\n\n\ndef test_catalog_rejects_provider_that_changes_view_name():\n    class BadProvider:\n        def read(self, request):\n            return PlanningContextView(view_name=\"system_state\", items=())\n\n    catalog = GovernedPlanningContextCatalog(providers={\"capabilities\": BadProvider()})\n    with pytest.raises(RuntimeError):\n        catalog.read(PlanningContextRequest(view_name=\"capabilities\"))\n\n\ndef test_request_limit_is_bounded():\n    with pytest.raises(ValueError):\n        PlanningContextRequest(view_name=\"capabilities\", limit=0)\n    with pytest.raises(ValueError):\n        PlanningContextRequest(view_name=\"capabilities\", limit=129)\n''', encoding='utf-8')

print(f'WROTE: {module.relative_to(root)}')
print(f'WROTE: {tests.relative_to(root)}')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Governed planning context view foundation added and validated."
echo "The reasoner can be given bounded, provider-neutral registry/state views without direct provider, connector, tool, agent, credential, or execution access."
echo "NO RUNTIME WIRING PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED PLANNING CONTEXT VIEWS =========="
