#!/usr/bin/env bash

# Project Jason targeted inspection: determine whether a plugin can emit native
# Microsoft Teams typing without patching OpenClaw core.
# Read-only.

set -u

OPENCLAW_ROOT="${OPENCLAW_ROOT:-/opt/jason/services/openclaw}"
HOOK_TYPES="$OPENCLAW_ROOT/src/plugins/hook-types.ts"
SDK_ROOT="$OPENCLAW_ROOT/src/plugin-sdk"
MSTEAMS_SRC="$OPENCLAW_ROOT/extensions/msteams/src"

echo "========== START TEAMS PLUGIN TYPING CAPABILITY INSPECTION =========="
echo

echo "========== SECTION 1: EXACT HOOK CONTEXT CONTRACTS =========="
if [ -f "$HOOK_TYPES" ]; then
  sed -n '1080,1215p' "$HOOK_TYPES"
else
  echo "ERROR: hook-types.ts not found"
fi
echo "========== END SECTION 1 =========="
echo

echo "========== SECTION 2: CANONICAL INBOUND MESSAGE CONTEXT =========="
for f in \
  "$OPENCLAW_ROOT/src/plugins/hook-message.types.ts" \
  "$OPENCLAW_ROOT/src/hooks/message-hook-mappers.ts" \
  "$OPENCLAW_ROOT/src/plugin-sdk/channel-inbound.ts"
do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    grep -n -A 80 -B 15 -E 'CanonicalInboundMessageHookContext|PluginHook.*Context|BuildChannelTurnContext|BuiltChannelTurnContext|turnContext|sendActivity|conversationRef|serviceUrl' "$f" 2>/dev/null | head -n 220 || true
  fi
done
echo "========== END SECTION 2 =========="
echo

echo "========== SECTION 3: MSTEAMS SEND/PROACTIVE EXPORTS =========="
grep -RniE \
  'export .*sendMSTeams|sendMSTeamsActivityWithReference|buildConversationReference|conversation reference|proactive' \
  "$MSTEAMS_SRC" \
  "$SDK_ROOT" \
  2>/dev/null | head -n 280 || true
echo "========== END SECTION 3 =========="
echo

echo "========== SECTION 4: PLUGIN RUNTIME CHANNEL SURFACE =========="
for f in \
  "$OPENCLAW_ROOT/src/plugins/runtime/types-channel.ts" \
  "$OPENCLAW_ROOT/src/plugins/runtime/runtime-channel.ts" \
  "$OPENCLAW_ROOT/src/plugin-sdk/channel-runtime.ts" \
  "$OPENCLAW_ROOT/src/plugin-sdk/channel-outbound.ts" \
  "$OPENCLAW_ROOT/src/plugin-sdk/channel-reply-core.ts"
do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    grep -n -A 100 -B 15 -E 'typing|send|activity|outbound|reply|channel:' "$f" 2>/dev/null | head -n 260 || true
  fi
done
echo "========== END SECTION 4 =========="
echo

echo "========== SECTION 5: MSTEAMS PACKAGE EXPORT MAP =========="
for f in \
  "$OPENCLAW_ROOT/extensions/msteams/package.json" \
  "$OPENCLAW_ROOT/extensions/msteams/index.ts" \
  "$OPENCLAW_ROOT/extensions/msteams/src/index.ts"
do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    cat "$f" | head -n 240
  fi
done
echo "========== END SECTION 5 =========="
echo

echo "========== SECTION 6: EXISTING ACK/REACTION/FEEDBACK PATTERNS =========="
grep -RniE \
  'message_received.*(ack|reaction|typing)|ack.*message_received|sendActivity\(\{ type: "typing"|feedbackEnabled|reaction' \
  "$OPENCLAW_ROOT/extensions" \
  "$OPENCLAW_ROOT/src/plugins" \
  2>/dev/null | head -n 260 || true
echo "========== END SECTION 6 =========="
echo

echo "========== RESULT =========="
echo "Read-only capability inspection complete."
echo "No files changed."
echo "========== END TEAMS PLUGIN TYPING CAPABILITY INSPECTION =========="
