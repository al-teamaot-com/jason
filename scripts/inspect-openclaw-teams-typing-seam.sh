#!/usr/bin/env bash

# Project Jason targeted inspection of the native OpenClaw Teams typing seam.
# Read-only. Shows only the source ranges needed to decide whether Jason can
# reuse native typing without patching OpenClaw core.

set -u

OPENCLAW_ROOT="${OPENCLAW_ROOT:-/opt/jason/services/openclaw}"
REPLY_DISPATCHER="$OPENCLAW_ROOT/extensions/msteams/src/reply-dispatcher.ts"
REPLY_TEST="$OPENCLAW_ROOT/extensions/msteams/src/reply-dispatcher.test.ts"
BRIDGE_DIR="${JASON_BRIDGE_DIR:-$OPENCLAW_ROOT/data/config/extensions/jason-bridge}"

clear
cd /home/al/projects/jason || exit 1

echo "========== START OPENCLAW TEAMS TYPING SEAM INSPECTION =========="
echo

echo "========== SECTION 1: NATIVE TYPING IMPLEMENTATION =========="
if [ -f "$REPLY_DISPATCHER" ]; then
  nl -ba "$REPLY_DISPATCHER" | sed -n '60,190p'
  echo
  nl -ba "$REPLY_DISPATCHER" | sed -n '280,340p'
else
  echo "ERROR: reply dispatcher not found: $REPLY_DISPATCHER"
fi
echo "========== END SECTION 1 =========="
echo

echo "========== SECTION 2: NATIVE TYPING TEST CONTRACT =========="
if [ -f "$REPLY_TEST" ]; then
  nl -ba "$REPLY_TEST" | sed -n '180,350p'
else
  echo "ERROR: reply dispatcher test not found: $REPLY_TEST"
fi
echo "========== END SECTION 2 =========="
echo

echo "========== SECTION 3: PLUGIN API CONTEXT TYPES =========="
grep -RniE \
  'type .*HookContext|interface .*HookContext|inbound_claim|before_agent_reply|message_received|turnContext|sendActivity|channelData' \
  "$OPENCLAW_ROOT/src/plugins" \
  "$OPENCLAW_ROOT/src" \
  2>/dev/null \
  | grep -E 'plugin|hook|context|inbound_claim|before_agent_reply|message_received|turnContext|sendActivity' \
  | head -n 260 || true
echo "========== END SECTION 3 =========="
echo

echo "========== SECTION 4: JASON BRIDGE IMPORTS AND HOOK REGISTRATION =========="
if [ -f "$BRIDGE_DIR/index.mjs" ]; then
  nl -ba "$BRIDGE_DIR/index.mjs" | sed -n '1,90p'
  echo
  nl -ba "$BRIDGE_DIR/index.mjs" | sed -n '400,545p'
else
  echo "ERROR: bridge index not found: $BRIDGE_DIR/index.mjs"
fi
echo "========== END SECTION 4 =========="
echo

echo "========== SECTION 5: SEARCH FOR REUSABLE EXPORTED TYPING SURFACE =========="
grep -RniE \
  'export .*typing|export .*sendTyping|create.*Typing|typing:[[:space:]]*\{|keepaliveIntervalMs|sendActivity\(\{ type: "typing"' \
  "$OPENCLAW_ROOT/extensions/msteams/src" \
  "$OPENCLAW_ROOT/src" \
  2>/dev/null | head -n 260 || true
echo "========== END SECTION 5 =========="
echo

echo "========== RESULT =========="
echo "Read-only seam inspection complete."
echo "No files changed."
echo "========== END OPENCLAW TEAMS TYPING SEAM INSPECTION =========="
