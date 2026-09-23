#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

BRANCH="feature/jason-runtime-service"
PROVEN_SOURCE="5b2c6c6"

echo "========== START RESOURCE LANGUAGE NORMALIZATION DOCUMENTATION CLOSEOUT =========="

echo "========== SECTION 1: PRECONDITIONS =========="
CURRENT_BRANCH="$(git branch --show-current)"
CURRENT_HEAD="$(git rev-parse --short HEAD)"
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  echo "ERROR: expected branch $BRANCH, found $CURRENT_BRANCH"
  exit 20
fi
if ! git merge-base --is-ancestor "$PROVEN_SOURCE" HEAD; then
  echo "ERROR: proven source checkpoint $PROVEN_SOURCE is not an ancestor of current HEAD $CURRENT_HEAD"
  exit 21
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: worktree/index is not clean."
  git status --short
  exit 22
fi
echo "PASS: current HEAD $CURRENT_HEAD contains live-proven source checkpoint $PROVEN_SOURCE"

echo "========== SECTION 2: UPDATE GOVERNING ENGINEERING CONTRACT =========="
python3 - <<'PY'
from pathlib import Path
p = Path('docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md')
s = p.read_text(encoding='utf-8')
anchor = '## Provider Adaptation Layer\n'
block = '''## Recognition Vocabulary and Canonical Evidence Facts\n\nHuman wording used to recognize a resource is not itself authoritative evidence vocabulary.\n\nCapability metadata therefore distinguishes:\n\n- `inquiry_hints` — words and phrases that identify the resource/capability being requested;\n- `fact_hints` — facts that the capability can return; and\n- `collection_fact` — the canonical collection evidence fact used when an exhaustive collection outcome is requested.\n\nThis separation prevents incidental fields from competing with the resource the human actually asked about. For example, a management-alert capability may return a `site` field, but the word `site` must not cause a request for Datto managed sites to resolve as an alert inquiry.\n\nFor exhaustive collection language such as `list every`, `list all`, or a count request, Jason normalizes recognized singular/plural/synonym wording to the governed `collection_fact` and carries the outcome contract through planning. A managed-site enumeration therefore resolves to the canonical `sites` fact with `result_intent=enumerate` and `completeness_requirement=complete`.\n\nThe rule is generic: recognition aliases help understand human language; canonical facts define what governed evidence must be retrieved. Do not create phrase-specific handlers for individual questions.\n\n'''
if block not in s:
    if anchor not in s:
        raise SystemExit('ERROR: engineering contract insertion anchor missing')
    s = s.replace(anchor, block + anchor, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: UPDATE CONSTRUCTION MAP =========="
python3 - <<'PY'
from pathlib import Path
p = Path('docs/control/EXTENSION-CONSTRUCTION-MAP.md')
s = p.read_text(encoding='utf-8')
old = '| Natural-language resource inquiry / evidence selection | `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` | Production endpoint inquiry, bounded evidence index, Ollama inquiry/evidence reasoners, runtime composition, focused tests | Separate selectors from facts; derive language vocabulary from governed capability metadata; request the smallest fact set; route only through Central Orchestrator; bound model evidence choices to Jason-supplied pointers; deterministic dereference; source attribution; no bespoke question-specific script |'
new = '| Natural-language resource inquiry / evidence selection | `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` and `docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md` | Production endpoint/site inquiries, deterministic metadata interpreter, bounded evidence index, Ollama fallback/evidence reasoners, runtime composition, focused tests | Separate selectors from facts; separate `inquiry_hints` from returnable `fact_hints`; declare canonical `collection_fact` for collection capabilities; normalize exhaustive/count language to canonical collection evidence; propagate result intent/completeness through planning; route only through Central Orchestrator; deterministic dereference/source attribution; no bespoke question-specific script |'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: construction-map resource inquiry row not found')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: UPDATE HISTORICAL PROOF =========="
python3 - <<'PY'
from pathlib import Path
p = Path('docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md')
s = p.read_text(encoding='utf-8')
block = '''\n## Varied-Language Complete Site Enumeration Proof\n\nA later production Teams test exposed a second language-contract defect using the request:\n\n`List every site in Datto RMM`\n\nBefore correction, Jason returned one scalar site identifier instead of the requested collection:\n\n`Requested resource — site: 59417980-b9eb-4c83-9080-f931cc210081. Source: datto_rmm.`\n\nThe failure was not treated as a standard-question problem. Investigation established two reusable contract issues:\n\n1. exhaustive collection wording could retain the matched singular language hint (`site`) instead of the capability's canonical collection fact (`sites`); and\n2. `site` also appeared as an incidental returnable fact on management alerts, so deterministic recognition could see competing candidates.\n\nThe reusable correction introduced/strengthened:\n\n- canonical `collection_fact` normalization for exhaustive collection/count outcomes;\n- propagation of `result_intent` and `completeness_requirement` through capability planning; and\n- separate `inquiry_hints` from broader `fact_hints`, so incidental return fields do not identify the wrong resource capability.\n\nFocused regression validation passed before deployment. The corrected runtime source checkpoint was committed and pushed as `5b2c6c6` (`Separate inquiry hints from resource fact hints`), rebuilt with the governed Jason runtime deployment helper, and passed runtime health verification.\n\nA subsequent production Microsoft Teams test of the same human request returned the complete site enumeration in the expected human-readable form. Operator acceptance: **PASS**.\n\nThis proof establishes the architectural rule that Jason must normalize varied human wording into governed resource/outcome contracts rather than depend on standard questions or phrase-specific scripts.\n'''
if '## Varied-Language Complete Site Enumeration Proof' not in s:
    s = s.rstrip() + '\n' + block
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: UPDATE CURRENT RESUME POINT =========="
python3 - <<'PY'
from pathlib import Path
p = Path('docs/control/CURRENT.md')
s = p.read_text(encoding='utf-8')
status_old = '**Status:** Teams → OpenClaw → Jason → Datto RMM resource inquiry is operationally proven for provider-backed semantic evidence selection. Runtime code used for the proof was deployed from an uncommitted worktree and still requires a separately authorized Git commit/push for source durability.'
status_new = '**Status:** Teams → OpenClaw → Jason → Datto RMM governed resource inquiry is operationally proven for varied human language, deterministic resource recognition, canonical collection outcomes, provider adaptation, complete managed-site enumeration, and source-attributed evidence. The latest live-proven source checkpoint is durable in GitHub at `5b2c6c6`.'
if status_old in s:
    s = s.replace(status_old, status_new, 1)
elif status_new not in s:
    raise SystemExit('ERROR: CURRENT status anchor not found')
marker = '<!-- END 2026-08-12 DATTO READ WORKSTREAM -->'
addition = '''\n\n## Latest durable success — varied-language complete collection interpretation\n\nThe production Teams request `List every site in Datto RMM` exposed and then verified correction of a generic language-contract defect. Jason now separates resource-recognition `inquiry_hints` from broader returnable `fact_hints`, normalizes exhaustive collection language to the capability's canonical `collection_fact`, and propagates `result_intent` plus `completeness_requirement` through planning.\n\nFor managed sites, exhaustive wording resolves to canonical `sites` evidence with `enumerate + complete`, allowing the existing Provider Adaptation layer to retrieve and verify the full authorized collection rather than rendering an incidental scalar `site` identifier.\n\nValidated/deployed source checkpoint: `5b2c6c6` (`Separate inquiry hints from resource fact hints`). Runtime rebuild/deployment and health verification passed. The same production Teams request was retested and operator-accepted as correct.\n\nDurable evidence: `docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md`.\n\nConstruction rule: recognition aliases are not evidence contracts. Future resource capabilities must distinguish recognition vocabulary from returnable facts and declare a canonical collection fact when they expose a collection. Representable varied/vague questions must be repaired at the reusable interpretation/capability/evidence layer, never with question-specific scripts.\n\nNext priority remains native Microsoft Teams processing feedback through OpenClaw's supported runtime/typing lifecycle.\n'''
if '## Latest durable success — varied-language complete collection interpretation' not in s:
    if marker not in s:
        raise SystemExit('ERROR: CURRENT Datto workstream marker missing')
    s = s.replace(marker, marker + addition, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 6: DOCUMENTATION IMPACT DETERMINATION =========="
echo "Architecture/engineering contract: UPDATED"
echo "Reusable construction guidance: UPDATED"
echo "System Registry: NO CHANGE — production topology/capability lifecycle did not change"
echo "Operations runbook: NO CHANGE — deployment procedure did not change"
echo "Historical proof/session evidence: UPDATED"
echo "Current resume point: UPDATED"
echo "New parallel authority: NONE"

echo "========== SECTION 7: VALIDATE DOCUMENTATION =========="
for f in \
  docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md \
  docs/control/EXTENSION-CONSTRUCTION-MAP.md \
  docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md \
  docs/control/CURRENT.md; do
  test -s "$f"
  if grep -nE '^(<<<<<<<|=======|>>>>>>>)' "$f"; then
    echo "ERROR: conflict marker found in $f"
    exit 30
  fi
  echo "PASS: $f ($(wc -l < "$f") lines)"
done

git diff --check

grep -q 'inquiry_hints' docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md
grep -q 'collection_fact' docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md
grep -q 'Varied-Language Complete Site Enumeration Proof' docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md
grep -q 'Latest durable success — varied-language complete collection interpretation' docs/control/CURRENT.md

echo "Documentation validation: PASS"

echo "========== SECTION 8: SHOW CHANGE STATE =========="
git status --short
git diff --stat

echo "========== FINAL STATUS =========="
echo "PASS: Standard Documentation Policy closeout prepared and validated."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END RESOURCE LANGUAGE NORMALIZATION DOCUMENTATION CLOSEOUT =========="
