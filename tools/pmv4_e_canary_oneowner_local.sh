#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
BUILD_SHA="$(basename "$DIR" | sed 's/^pmv4-e-canary-once-//')"
ROOT="$DIR/tools/pmv4_e_canary_oneowner_root.py"
OWNER="$DIR/tools/pmv4_e_canary_oneowner_owner.py"
MODE=""
if [ "$#" -gt 0 ]; then MODE="$1"; fi
case "$MODE" in
  --check-only)
    /usr/bin/python3 -B "$ROOT" --check-source --build-sha "$BUILD_SHA"
    sudo /usr/bin/python3 -I -B "$ROOT" --root-preflight --build-sha "$BUILD_SHA"
    ;;
  --execute)
    /usr/bin/python3 -B "$ROOT" --check-source --build-sha "$BUILD_SHA"
    sudo /usr/bin/python3 -I -B "$ROOT" --root-preflight --build-sha "$BUILD_SHA"
    /usr/bin/python3 -B "$OWNER" --approve --build-sha "$BUILD_SHA"
    sudo /usr/bin/python3 -I -B "$ROOT" --execute --build-sha "$BUILD_SHA"
    ;;
  --recover)
    sudo /usr/bin/python3 -I -B "$ROOT" --recover --build-sha "$BUILD_SHA"
    ;;
  *)
    echo "Usage: bash $0 --check-only|--execute|--recover" >&2
    exit 2
    ;;
esac
