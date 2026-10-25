#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <source|production> <source-revision> [workflow-run-id] [workflow-url]" >&2
  exit 64
fi

MODE="$1"
SOURCE_REVISION="$2"
WORKFLOW_RUN_ID="${3:-}"
WORKFLOW_URL="${4:-}"
REPO_ROOT="${JASON_DOCUMENTATION_REPO_ROOT:-/home/al/projects/jason}"
SHORT_REVISION="${SOURCE_REVISION:0:12}"
BRANCH="automation/documentation-reconcile-${SHORT_REVISION}"
WORKTREE_ROOT="${JASON_DOCUMENTATION_WORKTREE_ROOT:-/home/al/jason-worktrees}"
WORKTREE="$WORKTREE_ROOT/documentation-reconcile-${SHORT_REVISION}"

mkdir -p "$WORKTREE_ROOT"
# One host publisher at a time: source and production events share this lock.
exec 9>"$WORKTREE_ROOT/documentation-reconciliation.lock"
flock -x 9
cd "$REPO_ROOT"

# Reuse an existing generated PR instead of creating a PR per revision.
# An ambiguous set of PRs is a hard failure, never an invitation to pick one.
PR_ROWS="$(gh pr list --repo al-teamaot-com/jason --state open --limit 500 --json number,title,headRefName --jq '[.[] | select((.title | startswith("Reconcile automated documentation state for ")) and (.headRefName | startswith("automation/documentation-reconcile-")))]')"
PR_COUNT="$(printf '%s' "$PR_ROWS" | jq 'length')"
if [ "$PR_COUNT" -gt 1 ]; then
  echo "DOCUMENTATION_PUBLICATION=BLOCKED_MULTIPLE_CANDIDATES" >&2
  exit 1
fi
if [ "$PR_COUNT" -eq 1 ]; then
  BRANCH="$(printf '%s' "$PR_ROWS" | jq -r '.[0].headRefName')"
  PR_NUMBER="$(printf '%s' "$PR_ROWS" | jq -r '.[0].number')"
  # Protect against overwriting unrelated source or hand-authored material.
  CHANGED_PATHS="$(gh pr diff "$PR_NUMBER" --repo al-teamaot-com/jason --name-only)"
  while IFS= read -r changed; do
    case "$changed" in
      docs/control/AUTOMATED-CHANGE-STATE.json|docs/control/AUTOMATED-CHANGE-STATE.md) ;;
      *) echo "DOCUMENTATION_PUBLICATION=BLOCKED_NON_GENERATED_CHANGE" >&2; exit 1 ;;
    esac
  done <<< "$CHANGED_PATHS"
fi
git fetch origin main >/dev/null 2>&1
if [ "$PR_COUNT" -eq 1 ]; then
  git fetch origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" >/dev/null 2>&1
  # A delayed invocation must not replace a newer revision already offered.
  PRIOR_REVISION="$(git show "origin/$BRANCH:docs/control/AUTOMATED-CHANGE-STATE.json" | jq -r --arg mode "$MODE" 'if $mode == "source" then .validated_source.revision // "" else .production.revision // "" end')"
  if [ -n "$PRIOR_REVISION" ] && [ "$PRIOR_REVISION" != "$SOURCE_REVISION" ]; then
    if ! git cat-file -e "$PRIOR_REVISION^{commit}" 2>/dev/null; then
      git fetch origin "$PRIOR_REVISION" >/dev/null 2>&1 || { echo "DOCUMENTATION_PUBLICATION=BLOCKED_UNVERIFIABLE_PRIOR" >&2; exit 1; }
    fi
    if ! git merge-base --is-ancestor "$PRIOR_REVISION" "$SOURCE_REVISION"; then
      echo "DOCUMENTATION_PUBLICATION=BLOCKED_STALE_OR_DIVERGENT_REVISION" >&2
      exit 1
    fi
  fi
fi

if [ -d "$WORKTREE/.git" ] || [ -f "$WORKTREE/.git" ]; then
  git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
fi
rm -rf "$WORKTREE"

git branch -D "$BRANCH" >/dev/null 2>&1 || true
git worktree add -B "$BRANCH" "$WORKTREE" origin/main

cd "$WORKTREE"
git config user.name "Project Jason Documentation Automation"
git config user.email "jason@teamaot.com"
ARGS=("$MODE" --source-revision "$SOURCE_REVISION")
if [ "$MODE" = "source" ]; then
  ARGS+=(--workflow-run-id "$WORKFLOW_RUN_ID" --workflow-url "$WORKFLOW_URL")
fi
python3 tools/documentation_success_reconciler.py "${ARGS[@]}"
python3 tools/validate_documentation_control.py
git diff --check

CONTROL_BOARD_FILE="$(mktemp)"
cleanup_control_board() { rm -f "$CONTROL_BOARD_FILE"; }
trap cleanup_control_board EXIT
GITHUB_TOKEN="$(gh auth token)"
python3 tools/development_release_coordinator.py \
  --repository al-teamaot-com/jason \
  --token "$GITHUB_TOKEN" \
  --output "$CONTROL_BOARD_FILE"
unset GITHUB_TOKEN
# The board is advisory. Tag this specific production observation so that the
# GitHub scheduled publisher cannot replace it with older unmerged main data.
if [ "$MODE" = "production" ]; then
  printf '\n%s\n' '<!-- jason-host-production-report:v1 -->' >> "$CONTROL_BOARD_FILE"
fi
gh issue edit 526 --repo al-teamaot-com/jason --body-file "$CONTROL_BOARD_FILE" >/dev/null
echo "CONTROL_BOARD_PUBLICATION=PASS"

if git diff --quiet -- docs/control/AUTOMATED-CHANGE-STATE.json docs/control/AUTOMATED-CHANGE-STATE.md; then
  echo "DOCUMENTATION_PUBLICATION=NO_CHANGE"
  exit 0
fi

git add docs/control/AUTOMATED-CHANGE-STATE.json docs/control/AUTOMATED-CHANGE-STATE.md
git commit -m "Reconcile automated documentation state for ${SHORT_REVISION}"
git push --force-with-lease -u origin "$BRANCH"

PR_NUMBER="${PR_NUMBER:-}"
if [ -z "$PR_NUMBER" ]; then
  BODY_FILE="$(mktemp)"
  cat > "$BODY_FILE" <<EOF
## Organizational outcome

Automatically reconcile generated documentation state after a successful ${MODE} event.

## Documentation impact

- [x] Documentation updated
- [ ] No documentation impact

No-documentation-impact reason: Not applicable; this PR is the generated documentation reconciliation itself.

## Verification

- [x] Documentation build

Generated state is derived evidence only and does not alter Jason authority or narrative policy.
EOF
  PR_URL="$(gh pr create --repo al-teamaot-com/jason --base main --head "$BRANCH" --title "Reconcile automated documentation state for ${SHORT_REVISION}" --body-file "$BODY_FILE")"
  rm -f "$BODY_FILE"
  PR_NUMBER="$(gh pr view "$PR_URL" --repo al-teamaot-com/jason --json number --jq '.number')"
fi

echo "DOCUMENTATION_PUBLICATION=PR_OPEN"
echo "DOCUMENTATION_PR=$PR_NUMBER"
