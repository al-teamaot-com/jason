#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EVIDENCE DEPLOYMENT AND PROBE =========="

echo "========== SECTION 1: PRECONDITIONS =========="nBRANCH="$(git branch --show-current)"
HEAD="$(git rev-parse --short HEAD)"
echo "Branch: $BRANCH"
echo "HEAD: $HEAD"

if [[ "$BRANCH" != "feature/jason-runtime-service" ]]; then
  echo "ERROR: expected feature/jason-runtime-service."
  exit 20
fi

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before deployment."
  printf '%s\n' "$DIRTY"
  exit 21
fi

if [[ ! -x scripts/deploy-jason-runtime.sh ]]; then
  echo "ERROR: scripts/deploy-jason-runtime.sh is required."
  exit 22
fi

echo "========== SECTION 2: DEPLOY JASON RUNTIME =========="nbash scripts/deploy-jason-runtime.sh

echo "========== SECTION 3: DEPLOYMENT STATUS =========="nif command -v docker >/dev/null 2>&1; then
  docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
else
  echo "WARN: docker command unavailable for post-deploy status."
fi

echo "========== SECTION 4: LIVE PROBE INSTRUCTIONS =========="ncat <<'EOF'
Run these five questions through the normal Jason Teams interface, one at a time:

1. What is the Windows Display Version for AOT-50282?
2. What processor is on AOT-50282?
3. What CPU does AOT-50282 have?
4. How much RAM is in AOT-50282?
5. How much memory does AOT-50282 have?

Expected semantic behavior:
- Windows Display Version must come only from operating-system/windows-release evidence.
- Processor/CPU must resolve to processor model, not logical processor count.
- RAM/memory must resolve to total memory.
- If Datto does not expose a uniquely mapped provider value, Jason should fail closed rather than return an unrelated field.
EOF

echo "========== RESULT =========="necho "Deployment completed. Live semantic evidence questions are ready for Teams validation."
echo "NO SOURCE CHANGES PERFORMED."
echo "========== END DATTO SEMANTIC EVIDENCE DEPLOYMENT AND PROBE =========="
