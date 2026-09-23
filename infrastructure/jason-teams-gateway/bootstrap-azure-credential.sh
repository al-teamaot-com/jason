#!/usr/bin/env bash
set -eu

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"
SERVICE_DIR="${JASON_TEAMS_SERVICE_DIR:-/opt/jason/services/jason-teams-gateway}"
AZURE_CLI_IMAGE="${AZURE_CLI_IMAGE:-mcr.microsoft.com/azure-cli:latest}"
CREDENTIAL_YEARS="${JASON_TEAMS_CREDENTIAL_YEARS:-1}"
RUN_UID="$(id -u)"
RUN_GID="$(id -g)"

if ! docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: OpenClaw container not found: $OPENCLAW_CONTAINER"
  exit 1
fi

APP_ID="$(docker exec "$OPENCLAW_CONTAINER" openclaw config get channels.msteams.appId 2>/dev/null | tr -d '\r' | tail -n 1)"
TENANT_ID="$(docker exec "$OPENCLAW_CONTAINER" openclaw config get channels.msteams.tenantId 2>/dev/null | tr -d '\r' | tail -n 1)"

case "$APP_ID" in
  ????????-????-????-????-????????????) ;;
  *) echo "ERROR: could not resolve the configured Teams application id"; exit 1 ;;
esac
case "$TENANT_ID" in
  ????????-????-????-????-????????????) ;;
  *) echo "ERROR: could not resolve the configured Teams tenant id"; exit 1 ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
umask 077
PASSWORD_FILE="$TMP_DIR/password"
ENV_FILE="$TMP_DIR/msteams.env"

run_az() {
  if command -v az >/dev/null 2>&1; then
    az "$@"
  else
    mkdir -p "$HOME/.azure"
    docker run --rm -i \
      -v "$HOME/.azure:/root/.azure" \
      "$AZURE_CLI_IMAGE" \
      az "$@"
  fi
}

login_az() {
  if command -v az >/dev/null 2>&1; then
    az login \
      --tenant "$TENANT_ID" \
      --use-device-code \
      --only-show-errors \
      --output none
  else
    mkdir -p "$HOME/.azure"
    docker run --rm -it \
      -v "$HOME/.azure:/root/.azure" \
      "$AZURE_CLI_IMAGE" \
      az login \
      --tenant "$TENANT_ID" \
      --use-device-code \
      --only-show-errors \
      --output none
  fi
}

echo "========== JASON TEAMS CREDENTIAL BOOTSTRAP =========="
echo "APP_ID=$APP_ID"
echo "TENANT_ID=$TENANT_ID"
echo "Existing OpenClaw credentials will not be read, replaced, or deleted."
echo "A second credential will be appended for the direct Jason Teams gateway."

echo
echo "========== AZURE AUTHORITY CHECK =========="
if ! run_az account show --query tenantId -o tsv --only-show-errors >/dev/null 2>&1; then
  echo "Azure authentication is required. Complete the Microsoft device-login prompt below."
  login_az
fi

SIGNED_IN_TENANT="$(run_az account show --query tenantId -o tsv --only-show-errors | tr -d '\r')"
if [ "$(printf '%s' "$SIGNED_IN_TENANT" | tr '[:upper:]' '[:lower:]')" != "$(printf '%s' "$TENANT_ID" | tr '[:upper:]' '[:lower:]')" ]; then
  echo "Current Azure session is for a different tenant. Re-authenticating to the Teams tenant."
  login_az
fi

echo "PASS: Azure session is scoped to the configured Teams tenant"

echo
echo "========== APP REGISTRATION CHECK =========="
DISPLAY_NAME="$(run_az ad app show --id "$APP_ID" --query displayName -o tsv --only-show-errors 2>/dev/null || true)"
if [ -z "$DISPLAY_NAME" ]; then
  echo "ERROR: the configured Teams application could not be read in this tenant"
  exit 1
fi
echo "APP=$DISPLAY_NAME"

echo
echo "========== APPEND JASON-SPECIFIC CREDENTIAL =========="
if ! run_az ad app credential reset \
  --id "$APP_ID" \
  --append \
  --display-name "Project Jason Teams Gateway" \
  --years "$CREDENTIAL_YEARS" \
  --query password \
  -o tsv \
  --only-show-errors \
  > "$PASSWORD_FILE"
then
  echo "ERROR: Azure did not permit creation of the Jason Teams gateway credential"
  echo "The existing Teams credential was not modified."
  exit 1
fi

if [ ! -s "$PASSWORD_FILE" ]; then
  echo "ERROR: Azure returned an empty credential"
  exit 1
fi

PASSWORD="$(cat "$PASSWORD_FILE")"
printf 'MSTEAMS_APP_ID=%s\nMSTEAMS_TENANT_ID=%s\nMSTEAMS_APP_PASSWORD=%s\n' \
  "$APP_ID" "$TENANT_ID" "$PASSWORD" > "$ENV_FILE"
unset PASSWORD

sudo mkdir -p "$SERVICE_DIR"
sudo install -m 0600 -o "$RUN_UID" -g "$RUN_GID" \
  "$ENV_FILE" \
  "$SERVICE_DIR/msteams.env"

echo "PASS: dedicated Jason Teams credential created and stored with mode 0600"
echo "PASS: existing OpenClaw Teams credential remains intact"
echo "CREDENTIAL_BOOTSTRAP_STATUS=PASS"
