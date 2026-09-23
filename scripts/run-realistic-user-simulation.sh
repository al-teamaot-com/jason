#!/usr/bin/env bash
set -euo pipefail

clear

REPO="/home/al/projects/jason"
PY="$REPO/.venv/bin/python"
HARNESS="$REPO/tools/realistic_user_simulation.py"
SCENARIOS="$REPO/config/user_simulation/realistic-read-scenarios.json"

cd "$REPO"

echo "========== START REALISTIC USER SIMULATION =========="
echo "========== SOURCE STATE =========="
git rev-parse --short HEAD
git status --short

if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  echo "ERROR: Python 3 is required."
  exit 20
fi
if [ ! -f "$HARNESS" ]; then
  echo "ERROR: harness not found: $HARNESS"
  exit 21
fi
if [ ! -f "$SCENARIOS" ]; then
  echo "ERROR: scenario catalog not found: $SCENARIOS"
  exit 22
fi

echo "========== VALIDATE SCENARIO CATALOG =========="
"$PY" "$HARNESS" --scenarios "$SCENARIOS" --validate-scenarios

echo "========== RUN =========="
if [ "$#" -eq 0 ]; then
  echo "No response source supplied, so the harness will list the realistic scenarios only."
  echo "To evaluate captured Teams responses, pass: --responses <file.json|file.jsonl>"
  echo "To use an approved automated ingress driver, pass: --driver-command '<command>'"
  echo
  "$PY" "$HARNESS" --scenarios "$SCENARIOS" --list
else
  "$PY" "$HARNESS" --scenarios "$SCENARIOS" "$@"
fi

echo "========== END REALISTIC USER SIMULATION =========="
