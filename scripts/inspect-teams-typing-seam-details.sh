#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/jason/services/openclaw"

echo "========== START TEAMS TYPING SEAM DETAIL INSPECTION =========="

section() {
  echo
  echo "========== $1 =========="
}

section "SECTION 1: MSTEAMS REPLY DISPATCHER TYPING IMPLEMENTATION"
sed -n '1,230p' "$ROOT/extensions/msteams/src/reply-dispatcher.ts"

section "SECTION 2: PUBLIC TYPING CALLBACK CONTRACT"
grep -R -n -A120 -B20 \
  -e 'export function createTypingCallbacks' \
  -e 'export type CreateTypingCallbacksParams' \
  -e 'type CreateTypingCallbacksParams' \
  -e 'export type TypingCallbacks' \
  "$ROOT/src/channels/message" "$ROOT/src/channels/typing.ts" 2>/dev/null | head -n 500 || true

section "SECTION 3: REPLY DISPATCHER WITH TYPING CONTRACT"
grep -R -n -A160 -B30 \
  -e 'createReplyDispatcherWithTyping' \
  -e 'CreateReplyDispatcherWithTyping' \
  "$ROOT/src/auto-reply/reply" 2>/dev/null | head -n 650 || true

section "SECTION 4: MSTEAMS RUNTIME API EXPORTS"
for f in \
  "$ROOT/extensions/msteams/runtime-api.ts" \
  "$ROOT/extensions/msteams/channel-plugin-api.ts" \
  "$ROOT/extensions/msteams/src/runtime.ts"; do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    sed -n '1,260p' "$f"
  fi
done

section "SECTION 5: RUNTIME CONTEXT REGISTRATION USAGE"
grep -R -n -A80 -B20 \
  -e 'runtimeContexts.register' \
  -e 'runtimeContexts.get' \
  -e 'capability:.*typing' \
  -e 'capability:.*msteams' \
  "$ROOT/extensions" "$ROOT/src" 2>/dev/null | head -n 650 || true

section "SECTION 6: PROACTIVE TYPING ACTIVITY TEST/IMPLEMENTATION"
sed -n '70,135p' "$ROOT/extensions/msteams/src/reply-dispatcher.ts"
sed -n '220,310p' "$ROOT/extensions/msteams/src/sdk-proactive.ts"

echo
echo "========== RESULT =========="
echo "Read-only seam detail inspection complete."
echo "No files changed."
echo "========== END TEAMS TYPING SEAM DETAIL INSPECTION =========="
