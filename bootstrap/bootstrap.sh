#!/usr/bin/env bash
set -euo pipefail

MODE="check"
PROFILE="pilot"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: ./bootstrap/bootstrap.sh [--check|--install-missing|--start] [--profile pilot]

Modes:
  --check            Report missing prerequisites without changing the host.
  --install-missing  Install supported host prerequisites after explicit approval.
  --start            Validate prerequisites and start managed dependencies.

The bootstrap never initializes, unseals, or writes secrets to OpenBao.
Those actions require a separate authorized ceremony.
EOF
}

log() { printf '[jason-bootstrap] %s\n' "$*"; }
fail() { printf '[jason-bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --install-missing) MODE="install" ;;
    --start) MODE="start" ;;
    --profile) shift; PROFILE="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
  shift
done

[ "$PROFILE" = "pilot" ] || fail "Only the pilot profile is currently approved."

missing=()
command -v python3 >/dev/null 2>&1 || missing+=(python3)
command -v docker >/dev/null 2>&1 || missing+=(docker)
if command -v docker >/dev/null 2>&1; then
  docker compose version >/dev/null 2>&1 || missing+=(docker-compose-plugin)
fi

install_ubuntu_dependencies() {
  command -v apt-get >/dev/null 2>&1 || fail "Automatic prerequisite installation is currently supported only on Debian/Ubuntu."
  [ "$(id -u)" -eq 0 ] || fail "Run --install-missing with sudo."
  log "Installing approved host prerequisites."
  apt-get update
  apt-get install -y ca-certificates curl python3 python3-venv docker.io docker-compose-v2
  systemctl enable --now docker
}

if [ "${#missing[@]}" -gt 0 ]; then
  log "Missing prerequisites: ${missing[*]}"
  if [ "$MODE" = "install" ]; then
    install_ubuntu_dependencies
  else
    fail "Prerequisites are missing. Re-run with --install-missing only after reviewing the changes."
  fi
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required.")
PY

docker info >/dev/null 2>&1 || fail "Docker is installed but unavailable to this user or the daemon is stopped."
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable."

if [ "$MODE" = "check" ] || [ "$MODE" = "install" ]; then
  log "Prerequisite check passed. No secrets service was initialized or started."
  exit 0
fi

log "Starting OpenBao pilot dependency."
docker compose -f "$ROOT_DIR/deploy/openbao/compose.yaml" up -d
log "OpenBao container started on loopback only."
log "Initialization and unseal remain intentionally manual and governed."
