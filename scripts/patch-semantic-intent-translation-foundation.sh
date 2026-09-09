#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC INTENT TRANSLATION FOUNDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before semantic intent patch."
  printf '%s\n' "$DIRTY"
  exit 20
fi
echo "HEAD: $(git rev-parse --short HEAD)"

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: ADD WHOLE-PHRASE CANONICAL FACT NORMALIZATION =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/canonical_fact_vocabulary.py')
s = p.read_text(encoding='utf-8')
anchor = '''    def canonicalize(self, value: str) -> str:\n        definition = self.resolve(value)\n        return definition.canonical_fact if definition is not None else value.strip()\n'''
addition = '''    def canonicalize(self, value: str) -> str:\n        definition = self.resolve(value)\n        return definition.canonical_fact if definition is not None else value.strip()\n\n    def canonicalize_requested_facts(\n        self,\n        *,\n        human_text: str,\n        requested_facts: Iterable[str],\n    ) -> tuple[str, ...]:\n        \"\"\"Normalize reasoner fragments using explicit governed concepts in human text.\n\n        A language model may split one concept such as ``Windows Display Version``\n        into ``display`` and ``version``. Explicit canonical aliases in the original\n        human text outrank that fragmentation. This method never invents concepts that\n        are absent from the human request.\n        \"\"\"\n        normalized_text = self.normalize_text(human_text)\n        explicit: list[tuple[int, CanonicalFactDefinition]] = []\n        for alias, definition in self._aliases.items():\n            if not alias or not normalized_text:\n                continue\n            pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"\n            if re.search(pattern, normalized_text):\n                explicit.append((len(alias), definition))\n\n        if explicit:\n            explicit.sort(key=lambda item: item[0], reverse=True)\n            best_len = explicit[0][0]\n            best = {definition for length, definition in explicit if length == best_len}\n            if len(best) == 1:\n                definition = next(iter(best))\n                requested_words = {\n                    token\n                    for fact in requested_facts\n                    for token in self.normalize_text(str(fact)).split()\n                }\n                concept_words = set()\n                for raw in (definition.canonical_fact, *definition.aliases):\n                    concept_words.update(self.normalize_text(raw).split())\n                if requested_words and requested_words.issubset(concept_words):\n                    return (definition.canonical_fact,)\n\n        return tuple(self.canonicalize(str(item)) for item in requested_facts)\n'''
if 'def canonicalize_requested_facts(' not in s:
    if anchor not in s:
        raise SystemExit('ERROR: canonicalize anchor missing')
    s = s.replace(anchor, addition, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: USE ORIGINAL HUMAN TEXT TO NORMALIZE FACT CONCEPTS =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')
old = '''        normalized_facts = tuple(str(item).strip() for item in requested_facts)\n        if self.fact_vocabulary is not None:\n            normalized_facts = tuple(\n                self.fact_vocabulary.canonicalize(item)\n                for item in normalized_facts\n            )\n'''
new = '''        normalized_facts = tuple(str(item).strip() for item in requested_facts)\n        if self.fact_vocabulary is not None:\n            normalized_facts = self.fact_vocabulary.canonicalize_requested_facts(\n                human_text=text,\n                requested_facts=normalized_facts,\n            )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: fact normalization block missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: DECLARE USER-TO-ENDPOINT RELATIONSHIP SELECTOR =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_capability_catalog.py')
s = p.read_text(encoding='utf-8')
s = s.replace(
    '"selector_keys": "hostname,name,resource_id,site,serial_number",',
    '"selector_keys": "hostname,name,resource_id,site,serial_number,user_identity",',
    1,
)
old = '''                "organization, or authorization scope from an identifier prefix, suffix, naming "\n                "convention, or resemblance. Authorization scope is not supplied to this language "\n'''
# No source-specific logic here; the capability merely declares the relationship selector.
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: TEACH BOUNDED INTENT REASONER RELATIONSHIP SEMANTICS =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/ollama_reasoning.py')
s = p.read_text(encoding='utf-8')
needle = '''                "selector fields. Use execution_mode deterministic and permission_mode observe. "\n'''
replacement = '''                "selector fields. When the human asks which endpoint/device a named person or "\n                "account is on, using, associated with, or last logged into, represent the requested "\n                "resource as endpoint and put the human-supplied person/account text in the governed "\n                "user_identity selector when that selector is allowed. Ask for hostname/device name "\n                "as the requested fact. Never reinterpret the person's name as an endpoint name. "\n                "Use execution_mode deterministic and permission_mode observe. "\n'''
if replacement not in s:
    if needle not in s:
        raise SystemExit('ERROR: Ollama resource prompt anchor missing')
    s = s.replace(needle, replacement, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 6: ADD DATTO PROVIDER ADAPTATION FOR USER RELATIONSHIP DISCOVERY =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/connectors/datto_rmm/connector.py')
s = p.read_text(encoding='utf-8')

old = '''        search_request = self._prepare_provider_request(\n            capability="datto_rmm.device.search",\n            arguments=request.arguments,\n            credentials=credentials,\n            access_token=access_token,\n            token_type=token_type,\n        )\n        search_payload = self._execute_prepared_request(\n            request=request,\n            prepared=search_request,\n        )\n        discovery = self._normalize_result("datto_rmm.device.search", search_payload)\n        matches = discovery["resource_matches"]\n\n        hostname_reference = self._hostname_reference(request.arguments)\n'''
new = '''        user_reference = self._user_identity_reference(request.arguments)\n        if user_reference:\n            discovery = self._execute_user_identity_discovery(\n                request=request,\n                credentials=credentials,\n                access_token=access_token,\n                token_type=token_type,\n                user_reference=user_reference,\n            )\n            matches = discovery["resource_matches"]\n        else:\n            search_request = self._prepare_provider_request(\n                capability="datto_rmm.device.search",\n                arguments=request.arguments,\n                credentials=credentials,\n                access_token=access_token,\n                token_type=token_type,\n            )\n            search_payload = self._execute_prepared_request(\n                request=request,\n                prepared=search_request,\n            )\n            discovery = self._normalize_result("datto_rmm.device.search", search_payload)\n            matches = discovery["resource_matches"]\n\n        hostname_reference = self._hostname_reference(request.arguments)\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: device resolve discovery block missing')

anchor = '''    @staticmethod\n    def _hostname_reference(arguments: Mapping[str, Any]) -> str:\n'''
block = '''    def _execute_user_identity_discovery(\n        self,\n        *,\n        request: ConnectorRequest,\n        credentials: Mapping[str, str],\n        access_token: str,\n        token_type: str,\n        user_reference: str,\n    ) -> Mapping[str, Any]:\n        \"\"\"Resolve endpoint association from provider-reported user identity evidence.\n\n        Datto's account device collection exposes last-user evidence but does not expose\n        a provider search operator Jason can safely rely on for ordinary human identity\n        wording. Perform bounded complete discovery, compare only provider-returned user\n        evidence, preserve ambiguity, and never choose the first device.\n        \"\"\"\n        provider_pages: list[Any] = []\n        matches: list[Mapping[str, str]] = []\n        seen: set[str] = set()\n        discovery_complete = False\n\n        for page in range(1, self.fallback_discovery_max_pages + 1):\n            prepared = self._prepare_provider_request(\n                capability="datto_rmm.device.search",\n                arguments={"page": page, "max": self.fallback_discovery_page_size},\n                credentials=credentials,\n                access_token=access_token,\n                token_type=token_type,\n            )\n            payload = self._execute_prepared_request(request=request, prepared=prepared)\n            provider_pages.append(payload)\n            records = self._device_records(payload)\n            for record in records:\n                provider_user = self._first_scalar(\n                    record,\n                    "lastUser",\n                    "last_user",\n                    "lastLoggedInUser",\n                    "last_logged_in_user",\n                    "username",\n                    "userName",\n                )\n                if not provider_user or not self._user_identity_matches(\n                    reference=user_reference,\n                    provider_identity=provider_user,\n                ):\n                    continue\n                match = self._canonical_device_match(record)\n                resource_id = str(match.get("resource_id", "")).strip()\n                key = resource_id or f"{match.get('hostname', '').casefold()}|{match.get('site_id', '')}"\n                if key in seen:\n                    continue\n                seen.add(key)\n                matches.append(match)\n            if len(records) < self.fallback_discovery_page_size:\n                discovery_complete = True\n                break\n\n        return {\n            "resource_matches": matches,\n            "provider_data": {\n                "discovery_mode": "user_identity_relationship",\n                "pages": provider_pages,\n            },\n            "discovery_complete": discovery_complete,\n        }\n\n    @staticmethod\n    def _user_identity_reference(arguments: Mapping[str, Any]) -> str:\n        return str(arguments.get("user_identity") or "").strip()\n\n    @staticmethod\n    def _normalized_human_identity(value: str) -> str:\n        text = value.strip()\n        if "\\\\" in text:\n            text = text.rsplit("\\\\", 1)[-1]\n        elif "/" in text:\n            text = text.rsplit("/", 1)[-1]\n        if "@" in text:\n            text = text.split("@", 1)[0]\n        return "".join(ch for ch in text.casefold() if ch.isalnum())\n\n    @classmethod\n    def _user_identity_matches(cls, *, reference: str, provider_identity: str) -> bool:\n        left = cls._normalized_human_identity(reference)\n        right = cls._normalized_human_identity(provider_identity)\n        return bool(left and right and left == right)\n\n'''
if '_execute_user_identity_discovery(' not in s.split(anchor)[0]:
    if anchor not in s:
        raise SystemExit('ERROR: hostname reference anchor missing')
    s = s.replace(anchor, block + anchor, 1)

# user_identity is reasoning/provider-adaptation input and must never be blindly forwarded.
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 7: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_canonical_fact_vocabulary.py <<'PY'


def test_fragmented_windows_display_version_is_recombined_from_human_text():
    assert DEFAULT_CANONICAL_FACT_VOCABULARY.canonicalize_requested_facts(
        human_text="What is the Windows Display Version for AOT-50282?",
        requested_facts=("display", "version"),
    ) == ("operating system display version",)
PY

cat >> implementation/connectors/tests/test_datto_rmm_connector.py <<'PY'


def test_user_identity_matching_normalizes_domain_spacing_and_case():
    assert DattoRmmConnector._user_identity_matches(
        reference="Lindsey Collins",
        provider_identity="AzureAD\\LindseyCollins",
    )
    assert DattoRmmConnector._user_identity_matches(
        reference="al davis",
        provider_identity="AZUREAD\\AlDavis",
    )
    assert not DattoRmmConnector._user_identity_matches(
        reference="Lindsey Collins",
        provider_identity="AzureAD\\LindseyCole",
    )


def test_fact_bearing_user_relationship_discovery_preserves_provider_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "connectors.datto_rmm.connector.acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken("runtime-token"),
    )
    account_payload = {
        "devices": [
            {
                "uid": "device-lindsey",
                "hostname": "AOT-50001",
                "siteName": "AOT",
                "lastUser": "AzureAD\\LindseyCollins",
            },
            {
                "uid": "device-other",
                "hostname": "AOT-50002",
                "siteName": "AOT",
                "lastUser": "AzureAD\\OtherUser",
            },
        ]
    }
    exact_payload = {
        "uid": "device-lindsey",
        "hostname": "AOT-50001",
        "siteName": "AOT",
        "lastUser": "AzureAD\\LindseyCollins",
    }
    transport = Transport([account_payload, exact_payload])
    connector = DattoRmmConnector(secrets=Secrets(), transport=transport, audit=Audit())
    result = connector.execute(
        connector_request(
            arguments={
                "user_identity": "Lindsey Collins",
                "requested_facts": ("hostname",),
            }
        )
    )
    assert len(transport.calls) == 2
    assert "hostname" not in transport.calls[0]["params"]
    assert result.data["resolved_resource_id"] == "device-lindsey"
    assert result.data["resource_matches"] == [
        {"resource_id": "device-lindsey", "hostname": "AOT-50001", "site": "AOT"}
    ]
    assert result.data["provider_data"] == exact_payload
PY

echo "========== SECTION 8: VALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/orchestrator/resource_capability_catalog.py \
  implementation/connectors/datto_rmm/connector.py
$PY -m pytest -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/connectors/tests/test_datto_rmm_connector.py

echo "========== SECTION 9: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic intent translation foundation validated."
echo "Human fact phrases may normalize to one canonical concept even when reasoner output is fragmented."
echo "Person/account-to-endpoint questions may use provider-neutral user_identity relationship discovery."
echo "Datto matching is bounded, complete-aware, ambiguity-preserving, and provider evidence based."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END SEMANTIC INTENT TRANSLATION FOUNDATION =========="
