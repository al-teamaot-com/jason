#!/usr/bin/env bash
set -euo pipefail

JASON_REPO="${JASON_REPO:-/home/al/projects/jason}"
STATE_ROOT="${JASON_STATE_ROOT:-/var/lib/jason}"
AUTHORITY_DIR="$STATE_ROOT/authority"
OPENCLAW_DIR="$STATE_ROOT/openclaw"

pass() { printf '[PASS] %s\n' "$1"; }
info() { printf '[INFO] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; exit 1; }

printf '\033c'
printf '%s\n' '========================================================================'
printf '%s\n' 'PROJECT JASON - AUTHORITY / OPENCLAW HOST PREPARATION'
printf '%s\n' '========================================================================'
printf '\n'

[ -d "$JASON_REPO/.git" ] || fail "Jason repository not found: $JASON_REPO"
cd "$JASON_REPO"
pass "Working directory: $(pwd)"

command -v python3 >/dev/null 2>&1 || fail 'python3 is required'
pass "Python: $(python3 --version 2>&1)"

info 'Preparing governed state directories (sudo may prompt)...'
sudo install -d -m 0750 -o al -g al "$STATE_ROOT"
sudo install -d -m 0700 -o al -g al "$AUTHORITY_DIR"
sudo install -d -m 0700 -o al -g al "$OPENCLAW_DIR"
pass "Authority state directory: $AUTHORITY_DIR"
pass "OpenClaw state directory: $OPENCLAW_DIR"

AUTHORITY_DB="$AUTHORITY_DIR/authority.sqlite3"
PYTHONPATH="implementation" python3 tools/identity_authority_admin.py \
  --database "$AUTHORITY_DB" health
chmod 0600 "$AUTHORITY_DB"
pass 'Authority database initialized with owner-only file permissions'

REPLAY_DB="$OPENCLAW_DIR/replay.sqlite3"
SECURITY_AUDIT_DB="$OPENCLAW_DIR/security-audit.sqlite3"

info "Reserved replay path: $REPLAY_DB"
info "Reserved pre-orchestration audit path: $SECURITY_AUDIT_DB"
info 'No OpenClaw private key was generated.'
info 'No provider credential was resolved.'
info 'No network request was made by this preparation script.'

printf '\n%s\n' '========================================================================'
printf '%s\n' 'HOST PREPARATION COMPLETE'
printf '%s\n' '========================================================================'
printf '[INFO] Branch: %s\n' "$(git branch --show-current)"
printf '[INFO] HEAD:   %s\n' "$(git rev-parse --short HEAD)"
printf '[INFO] Next:   generate/provision OpenClaw machine identity only after runtime location is confirmed\n'
