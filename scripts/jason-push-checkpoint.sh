#!/usr/bin/env bash

# Project Jason safe checkpoint push helper.
# Synchronizes the current branch with origin and pushes without force.
# It intentionally refuses to continue when the worktree is dirty or a
# reconciliation requires human review.

set -u

REMOTE="${JASON_GIT_REMOTE:-origin}"
BRANCH="$(git branch --show-current 2>/dev/null || true)"

if [ -z "$BRANCH" ]; then
  echo "ERROR: no current Git branch"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: worktree/index contains uncommitted changes. Commit the validated checkpoint first."
  git status --short
  exit 1
fi

if ! git diff --check; then
  echo "ERROR: git diff --check failed"
  exit 1
fi

echo "Branch: $BRANCH"
echo "Fetching $REMOTE/$BRANCH ..."

if ! git fetch "$REMOTE" "$BRANCH"; then
  echo "ERROR: fetch failed"
  exit 1
fi

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "$REMOTE/$BRANCH")"
BASE_SHA="$(git merge-base HEAD "$REMOTE/$BRANCH")"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "PASS: local and remote are already synchronized at ${LOCAL_SHA:0:7}."
  exit 0
fi

if [ "$LOCAL_SHA" = "$BASE_SHA" ]; then
  echo "Local branch is behind remote. Fast-forwarding..."
  if ! git merge --ff-only "$REMOTE/$BRANCH"; then
    echo "ERROR: fast-forward failed"
    exit 1
  fi
elif [ "$REMOTE_SHA" = "$BASE_SHA" ]; then
  echo "Local branch is ahead of remote. Ready to push."
else
  echo "Local and remote have diverged. Rebasing local validated commits onto remote..."
  if ! GIT_EDITOR=true git rebase "$REMOTE/$BRANCH"; then
    echo "ERROR: rebase requires review. Resolve or abort the rebase before retrying."
    exit 2
  fi
fi

if ! git diff --check; then
  echo "ERROR: post-reconciliation git diff --check failed"
  exit 1
fi

if ! git push "$REMOTE" "$BRANCH"; then
  echo "ERROR: push failed"
  exit 1
fi

FINAL_LOCAL="$(git rev-parse HEAD)"
FINAL_REMOTE="$(git rev-parse "$REMOTE/$BRANCH")"

if [ "$FINAL_LOCAL" != "$FINAL_REMOTE" ]; then
  echo "ERROR: push returned success but local/remote SHAs differ"
  exit 1
fi

echo "PASS: $BRANCH synchronized to ${FINAL_LOCAL:0:7}."
