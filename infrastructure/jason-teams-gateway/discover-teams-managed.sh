#!/usr/bin/env bash
set -eu

TEAMS_CLI_IMAGE="${TEAMS_CLI_IMAGE:-node:24-bookworm-slim}"
EXPECTED_CLIENT_ID="${JASON_TEAMS_CLIENT_ID:-c94301b7-7194-46ab-aab7-94f9366f51a9}"

cat <<EOF
========== TEAMS-MANAGED BOT DISCOVERY ==========
The Azure Bot lookup returned no resource because this deployment may use a
Teams-managed bot. Microsoft Teams Developer CLI manages those registrations
without an Azure Bot Service resource.

Expected Microsoft Entra / bot client id:
$EXPECTED_CLIENT_ID

This operation is read-only. It does not update the bot endpoint or manifest.
EOF

echo
echo "========== START TEAMS DEVELOPER CLI =========="
echo "A Microsoft device-login prompt will appear. Sign in to the AOT tenant account that can manage the Teams app."
echo "After login, the CLI will list apps and then open an app picker."
echo "Select the Jason/OpenClaw app associated with the client id shown above."

docker run --rm -it \
  -e EXPECTED_CLIENT_ID="$EXPECTED_CLIENT_ID" \
  "$TEAMS_CLI_IMAGE" \
  sh -lc '
    set -eu
    npm install -g @microsoft/teams.cli@latest --no-audit --no-fund >/dev/null 2>&1

    echo
    echo "========== TEAMS CLI LOGIN =========="
    teams login --device-code

    echo
    echo "========== TEAMS CLI STATUS =========="
    teams status

    echo
    echo "========== REGISTERED TEAMS APPS =========="
    teams app list

    echo
    echo "========== SELECT JASON / OPENCLAW APP =========="
    echo "Expected bot/client id: $EXPECTED_CLIENT_ID"
    echo "Choose the app used by the current Jason/OpenClaw Teams conversation."
    echo
    teams app get --json appId,teamsAppId,name,endpoint
  '

echo
echo "DISCOVERY_STATUS=PASS"
echo "No Teams app, bot endpoint, OpenClaw, Docker, or Jason configuration was changed."
