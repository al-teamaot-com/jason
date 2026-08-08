#!/usr/bin/env bash
set -u

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[FAIL] CatchMeUp must be run from inside the Jason repository." >&2
  exit 2
fi

cd "$REPO_ROOT" || exit 2

CHECKPOINT="08-Session-Records/CURRENT.md"
COLLECTOR="tools/catch_me_up.py"

echo "# Project Jason — Session Resume Brief"
echo
if [[ -f "$CHECKPOINT" ]]; then
  cat "$CHECKPOINT"
else
  echo "> [WARN] Canonical checkpoint is missing: $CHECKPOINT"
fi

echo
echo "---"
echo
echo "# Project Jason — Detailed Host / Repository Snapshot"
echo

if [[ ! -f "$COLLECTOR" ]]; then
  echo "[FAIL] Detailed collector is missing: $COLLECTOR" >&2
  exit 3
fi

python3 "$COLLECTOR" --stdout-only
RESULT=$?

echo
if [[ $RESULT -eq 0 ]]; then
  echo "[PASS] PROJECT JASON CATCHMEUP COMPLETE"
else
  echo "[FAIL] PROJECT JASON CATCHMEUP FAILED — collector exit code $RESULT"
fi

exit $RESULT
