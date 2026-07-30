#!/usr/bin/env bash
set -euo pipefail

MODE="check"
PROFILE="pilot"
SECRETS_PROVIDER="external"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: ./bootstrap/bootstrap.sh [--check|--install-missing|--start] [--profile pilot] [--secrets-provider external|openbao|none]

Modes:
  --check            Report missing prerequisites without changing the host.
  --install-missing  Install supported host prerequisites after explicit approval.
  --start            Validate prerequisites and start only explicitly selected managed dependencies.

Secrets providers:
  external           Use an externally managed secrets service. This is the default.
  openbao            Start the repository's optional OpenBao reference deployment.
  none               Start no secrets service. Suitable only for tests using synthetic providers.

The bootstrap never initializes, unseals, authenticates to, or writes secrets into any provider.
Provider enrollment and secret population require a separate authorized process.
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
    --secrets-provider) shift; SECRETS_PROVIDER="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
  shift
done

[ "$PROFILE" = "pilot" ] || fail "Only the pilot profile is currently approved."
case "$SECRETS_PROVIDER" in
  external|openbao|none) ;;
  *) fail "Unsupported secrets provider: $SECRETS_PROVIDER" ;;
esac

missing=()
command -v python3 >/dev/null 2>&1 || missing+=(python3)

if [ "$SECRETS_PROVIDER" = "openbao" ]; then
  command -v docker >/dev/null 2>&1 || missing+=(docker)
  if command -v docker >/dev/null 2>&1; then
    docker compose version >/dev/null 2>&1 || missing+=(docker-compose-plugin)
  fi
fi

install_ubuntu_dependencies() {
  command -v apt-get >/dev/null 2>&1 || fail "Automatic prerequisite installation is currently supported only on Debian/Ubuntu."
  [ "$(id -u)" -eq 0 ] || fail "Run --install-missing with sudo."
  log "Installing approved host prerequisites."
  apt-get update
  apt-get install -y ca-certificates curl python3 python3-venv
  if [ "$SECRETS_PROVIDER" = "openbao" ]; then
    apt-get install -y docker.io docker-compose-v2
    systemctl enable --now docker
  fi
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

if [ "$SECRETS_PROVIDER" = "openbao" ]; then
  docker info >/dev/null 2>&1 || fail "Docker is installed but unavailable to this user or the daemon is stopped."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable."
fi

if [ "$MODE" = "check" ] || [ "$MODE" = "install" ]; then
  log "Prerequisite check passed for secrets provider: $SECRETS_PROVIDER."
  exit 0
fi

case "$SECRETS_PROVIDER" in
  openbao)
    log "Starting optional OpenBao reference deployment."
    docker compose -f "$ROOT_DIR/deploy/openbao/compose.yaml" up -d
    log "OpenBao container started on loopback only. Initialization and unseal remain manual and governed."
    ;;
  external)
    log "External secrets provider selected. No secrets service will be installed or started."
    ;;
  none)
    log "No secrets provider selected. Only synthetic or test providers may be used."
    ;;
esac
