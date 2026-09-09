#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/jason/services/openclaw"

echo "========== START TEAMS RUNTIME CONTEXT INSERTION INSPECTION =========="

section() {
  echo
  echo "========== $1 =========="
}

section "SECTION 1: MSTEAMS MONITOR ENTRYPOINTS"
grep -R -n -A140 -B30 \
  -e 'monitorMSTeams' \
  -e 'monitor.*MSTeams' \
  -e 'start.*MSTeams' \
  -e 'channelRuntime' \
  "$ROOT/extensions/msteams/src" 2>/dev/null | head -n 900 || true

section "SECTION 2: MSTEAMS INBOUND DISPATCHER CREATION CALLS"
grep -R -n -A100 -B50 \
  -e 'createMSTeamsReplyDispatcher' \
  "$ROOT/extensions/msteams/src" 2>/dev/null | head -n 700 || true

section "SECTION 3: CHANNEL RUNTIME TYPE AND PLUGIN SERVICE CONTRACT"
grep -R -n -A120 -B30 \
  -e 'channelRuntime.*ChannelRuntime' \
  -e 'ChannelRuntimeSurface' \
  -e 'startAccount' \
  -e 'stopAccount' \
  "$ROOT/src/channels/plugins" "$ROOT/src/plugins" 2>/dev/null | head -n 900 || true

section "SECTION 4: MSTEAMS ACCOUNT MONITOR ABORT LIFETIME"
grep -R -n -A140 -B40 \
  -e 'abortSignal' \
  -e 'AbortSignal' \
  -e 'onReady' \
  "$ROOT/extensions/msteams/src" 2>/dev/null | head -n 900 || true

section "SECTION 5: EXISTING RUNTIME CONTEXT HELPERS EXPORTED TO PLUGINS"
grep -R -n -A100 -B20 \
  -e 'registerChannelRuntimeContext' \
  -e 'getChannelRuntimeContext' \
  -e 'watchChannelRuntimeContexts' \
  "$ROOT/src/plugin-sdk" "$ROOT/src/plugins" "$ROOT/package.json" 2>/dev/null | head -n 700 || true

section "SECTION 6: MSTEAMS CONVERSATION STORE ACCESS"
grep -R -n -A120 -B30 \
  -e 'StoredConversationReference' \
  -e 'conversationRef' \
  -e 'conversation-store' \
  "$ROOT/extensions/msteams/src" 2>/dev/null | head -n 900 || true

echo
echo "========== RESULT =========="
echo "Read-only Teams runtime-context insertion inspection complete."
echo "No files changed."
echo "========== END TEAMS RUNTIME CONTEXT INSERTION INSPECTION =========="
