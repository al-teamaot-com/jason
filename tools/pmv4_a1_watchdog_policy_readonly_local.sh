#!/usr/bin/env bash
# Exact A1 watchdog root policy review only. DOES NOT UPDATE PRODUCTION.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--inspect-root" ) ]] ||
  { echo "A1_WATCHDOG_READ=DENIED INVALID_MODE" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "A1_WATCHDOG_READ=DENIED OWNER_LOCAL_UID_REQUIRED" >&2; exit 2; }

TREE="/srv/jason/archive/engineering-worktrees/pmv4-a1-watchdog-allowlist-20261116"
REVIEW="$TREE/tools/pmv4_a1_watchdog_policy_review.py"
SOURCE="$TREE/config/production-desired-state.json"
ROOT="/run/jason-pmv4-a1-watchdog-review-8c20"
STAGED="$ROOT/pmv4_a1_watchdog_policy_review.py"
PROPOSED="$ROOT/proposed-desired-state.json"
REVIEW_SHA="59dcf9c5f56bbb5cd932b2ffd0025a87348d7bb1ac034de9fc353ed9cb6b5e6c"
SOURCE_SHA="db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50"
BASE="8c2064193d74cc41b52369681febbc0a74fa96f7"

hash_check() {
  printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status
}
hash_check "$REVIEW_SHA" "$REVIEW"
hash_check "$SOURCE_SHA" "$SOURCE"
[[ "$(gh api repos/al-teamaot-com/jason/branches/main --jq .commit.sha)" == "$BASE" ]] ||
  { echo "A1_WATCHDOG_READ=DENIED PROTECTED_SOURCE_CHANGED" >&2; exit 2; }
[[ ! -e "$ROOT" && ! -L "$ROOT" ]] ||
  { echo "A1_WATCHDOG_READ=DENIED PREEXISTING_TRUST_STAGE" >&2; exit 2; }
cd "$TREE"
PYTHONPATH=tools:. /usr/bin/python3 -B -m pytest -q \
  tests/test_pmv4_a1_watchdog_allowlist.py \
  tests/test_pmv4_a1_watchdog_policy_review.py
echo "A1_WATCHDOG_EXACT_SOURCE_PREVIEW=PASS"
echo "OWNER_APPROVAL_USED=false; LIVE_POLICY_CHANGES=false"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi

[[ -t 0 && -t 1 ]] ||
  { echo "A1_WATCHDOG_READ=DENIED LOCAL_INTERACTIVE_TTY_REQUIRED" >&2; exit 2; }
STAGED_TEMP=0
cleanup() {
  if [[ "$STAGED_TEMP" == 1 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED" "$PROPOSED"
    sudo /usr/bin/rmdir -- "$ROOT"
  fi
}
trap cleanup EXIT
sudo /usr/bin/install -d -o root -g root -m 0700 "$ROOT"
STAGED_TEMP=1
sudo /usr/bin/install -o root -g root -m 0400 "$REVIEW" "$STAGED"
sudo /usr/bin/install -o root -g root -m 0400 "$SOURCE" "$PROPOSED"
printf '%s  %s\n' "$REVIEW_SHA" "$STAGED" |
  sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$SOURCE_SHA" "$PROPOSED" |
  sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGED" --read-only
echo "A1_WATCHDOG_ROOT_READ_ONLY_PROOF=RECORDED"
echo "NO_OWNER_AUTH_OR_PRODUCTION_MUTATIONS=true"
