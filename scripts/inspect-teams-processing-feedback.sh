#!/usr/bin/env bash

# Project Jason targeted inspection for Teams processing feedback.
# Read-only. Produces only the bridge/typing lifecycle evidence needed to wire
# native OpenClaw Teams typing into the Jason bridge.

set -u

OPENCLAW_ROOT="${OPENCLAW_ROOT:-/opt/jason/services/openclaw}"
BRIDGE_DIR="${JASON_BRIDGE_DIR:-$OPENCLAW_ROOT/data/config/extensions/jason-bridge}"
MSTEAMS_DIR="$OPENCLAW_ROOT/extensions/msteams/src"

echo "========== START TEAMS PROCESSING FEEDBACK INSPECTION =========="
echo

echo "========== SECTION 1: ACTIVE JASON BRIDGE FORWARDING HOOKS =========="
if [ -f "$BRIDGE_DIR/index.mjs" ]; then
  grep -n -A 45 -B 20 -E \
    'forwardGovernedTeamsTurn|inbound_claim|before_agent_reply|registerHook|register.*hook' \
    "$BRIDGE_DIR/index.mjs" 2>/dev/null | head -n 260 || true
else
  echo "ERROR: active bridge index not found: $BRIDGE_DIR/index.mjs"
fi
echo "========== END SECTION 1 =========="
echo

echo "========== SECTION 2: BRIDGE CORE FORWARDER =========="
if [ -f "$BRIDGE_DIR/bridge-core.mjs" ]; then
  grep -n -A 90 -B 25 -E \
    'forwardGovernedTeamsTurn|fetch\(|runtime|conversation|reply|message' \
    "$BRIDGE_DIR/bridge-core.mjs" 2>/dev/null | head -n 320 || true
else
  echo "ERROR: bridge core not found: $BRIDGE_DIR/bridge-core.mjs"
fi
echo "========== END SECTION 2 =========="
echo

echo "========== SECTION 3: NATIVE MSTEAMS TYPING LIFECYCLE =========="
if [ -d "$MSTEAMS_DIR" ]; then
  grep -RniE \
    'sendActivity\(.*typing|type:[[:space:]]*["'"']typing["'"']|typingInterval|typing.*interval|sendTyping|startTyping|stopTyping' \
    "$MSTEAMS_DIR" 2>/dev/null | head -n 220 || true
else
  echo "ERROR: msteams source directory not found: $MSTEAMS_DIR"
fi
echo "========== END SECTION 3 =========="
echo

echo "========== SECTION 4: PLUGIN/HANDLER CONTEXT SURFACE =========="
grep -RniE \
  'before_agent_reply|inbound_claim|sendActivity|channelData|turnContext|activity|replyToId|context\.send' \
  "$OPENCLAW_ROOT/src" \
  "$OPENCLAW_ROOT/extensions/msteams/src" \
  2>/dev/null | grep -E 'hook|plugin|reply|typing|msteams|context|activity' | head -n 320 || true
echo "========== END SECTION 4 =========="
echo

echo "========== SECTION 5: BRIDGE TEST SURFACE =========="
if [ -d "$BRIDGE_DIR/test" ]; then
  find "$BRIDGE_DIR/test" -maxdepth 2 -type f -print 2>/dev/null | sort
  echo
  grep -RniE \
    'forwardGovernedTeamsTurn|inbound_claim|before_agent_reply|reply|typing|activity' \
    "$BRIDGE_DIR/test" 2>/dev/null | head -n 260 || true
else
  echo "No bridge test directory found."
fi
echo "========== END SECTION 5 =========="
echo

echo "========== RESULT =========="
echo "Read-only inspection complete."
echo "No files changed."
echo "========== END TEAMS PROCESSING FEEDBACK INSPECTION =========="
