#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== START USER RELATIONSHIP PROVIDER ADAPTATION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: REPAIR MISSING DATTO RELATIONSHIP METHODS =========="
$PY - <<'PY'
from pathlib import Path

p = Path('implementation/connectors/datto_rmm/connector.py')
s = p.read_text(encoding='utf-8')

if '    def _execute_user_identity_discovery(' not in s:
    anchor = '''    @staticmethod\n    def _hostname_reference(arguments: Mapping[str, Any]) -> str:\n'''
    block = '''    def _execute_user_identity_discovery(\n        self,\n        *,\n        request: ConnectorRequest,\n        credentials: Mapping[str, str],\n        access_token: str,\n        token_type: str,\n        user_reference: str,\n    ) -> Mapping[str, Any]:\n        \"\"\"Resolve endpoint association from provider-reported user identity evidence.\n\n        The provider-neutral contract supplies ``user_identity``. Datto adaptation\n        performs bounded account discovery and compares only provider-returned user\n        evidence. It preserves ambiguity and never selects the first device.\n        \"\"\"\n        provider_pages: list[Any] = []\n        matches: list[Mapping[str, str]] = []\n        seen: set[str] = set()\n        discovery_complete = False\n\n        for page in range(1, self.fallback_discovery_max_pages + 1):\n            prepared = self._prepare_provider_request(\n                capability="datto_rmm.device.search",\n                arguments={"page": page, "max": self.fallback_discovery_page_size},\n                credentials=credentials,\n                access_token=access_token,\n                token_type=token_type,\n            )\n            payload = self._execute_prepared_request(request=request, prepared=prepared)\n            provider_pages.append(payload)\n            records = self._device_records(payload)\n\n            for record in records:\n                provider_user = self._first_scalar(\n                    record,\n                    "lastUser",\n                    "last_user",\n                    "lastLoggedInUser",\n                    "last_logged_in_user",\n                    "username",\n                    "userName",\n                )\n                if not provider_user or not self._user_identity_matches(\n                    reference=user_reference,\n                    provider_identity=provider_user,\n                ):\n                    continue\n\n                match = self._canonical_device_match(record)\n                resource_id = str(match.get("resource_id", "")).strip()\n                key = resource_id or f"{match.get('hostname', '').casefold()}|{match.get('site_id', '')}"\n                if key in seen:\n                    continue\n                seen.add(key)\n                matches.append(match)\n\n            if len(records) < self.fallback_discovery_page_size:\n                discovery_complete = True\n                break\n\n        return {\n            "resource_matches": matches,\n            "provider_data": {\n                "discovery_mode": "user_identity_relationship",\n                "pages": provider_pages,\n            },\n            "discovery_complete": discovery_complete,\n        }\n\n    @staticmethod\n    def _user_identity_reference(arguments: Mapping[str, Any]) -> str:\n        return str(arguments.get("user_identity") or "").strip()\n\n    @staticmethod\n    def _normalized_human_identity(value: str) -> str:\n        text = value.strip()\n        if "\\\\" in text:\n            text = text.rsplit("\\\\", 1)[-1]\n        elif "/" in text:\n            text = text.rsplit("/", 1)[-1]\n        if "@" in text:\n            text = text.split("@", 1)[0]\n        return "".join(ch for ch in text.casefold() if ch.isalnum())\n\n    @classmethod\n    def _user_identity_matches(cls, *, reference: str, provider_identity: str) -> bool:\n        left = cls._normalized_human_identity(reference)\n        right = cls._normalized_human_identity(provider_identity)\n        return bool(left and right and left == right)\n\n'''
    if anchor not in s:
        raise SystemExit('ERROR: hostname reference anchor missing')
    s = s.replace(anchor, block + anchor, 1)
    p.write_text(s, encoding='utf-8')
    print('REPAIRED:', p)
else:
    print('PASS: relationship methods already present')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check
$PY -m py_compile implementation/connectors/datto_rmm/connector.py

echo "========== SECTION 4: FOCUSED TESTS =========="
$PY -m pytest -q \
  implementation/connectors/tests/test_datto_rmm_connector.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic intent translation foundation repaired and validated."
echo "The prior failure was a patch-helper insertion guard bug; the relationship methods were never inserted."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END USER RELATIONSHIP PROVIDER ADAPTATION REPAIR =========="
