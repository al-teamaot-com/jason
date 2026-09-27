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
cd "$REPO_ROOT"
git fetch origin main "$BRANCH" >/dev/null 2>&1 || git fetch origin main >/dev/null 2>&1

if [ -d "$WORKTREE/.git" ] || [ -f "$WORKTREE/.git" ]; then
  git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
fi
rm -rf "$WORKTREE"

if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git worktree add -B "$BRANCH" "$WORKTREE" "origin/$BRANCH"
  git -C "$WORKTREE" rebase origin/main
else
  git branch -D "$BRANCH" >/dev/null 2>&1 || true
  git worktree add -b "$BRANCH" "$WORKTREE" origin/main
fi

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

if git diff --quiet -- docs/control/AUTOMATED-CHANGE-STATE.json docs/control/AUTOMATED-CHANGE-STATE.md; then
  echo "DOCUMENTATION_PUBLICATION=NO_CHANGE"
  exit 0
fi

git add docs/control/AUTOMATED-CHANGE-STATE.json docs/control/AUTOMATED-CHANGE-STATE.md
git commit -m "Reconcile automated documentation state for ${SHORT_REVISION}"
git push --force-with-lease -u origin "$BRANCH"

PR_NUMBER="$(gh pr list --repo al-teamaot-com/jason --head "$BRANCH" --state open --json number --jq '.[0].number // empty')"
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
