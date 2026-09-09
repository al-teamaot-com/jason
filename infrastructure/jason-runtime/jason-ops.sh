#!/usr/bin/env bash

# Jason runtime operator helper.
# Keeps routine deploy/status/capture work short and repeatable without exposing secrets.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infrastructure/jason-runtime/compose.yaml"
RUNTIME_CONTAINER="jason-runtime"
GATEWAY_CONTAINER="jason-teams-gateway"
OLLAMA_CONTAINER="jason-ollama"
JASON_COMPOSE_OVERRIDE_FILE=""

usage() {
    cat <<'EOF'
Usage:
  bash infrastructure/jason-runtime/jason-ops.sh status
  bash infrastructure/jason-runtime/jason-ops.sh deploy
  bash infrastructure/jason-runtime/jason-ops.sh baseline-deploy
  bash infrastructure/jason-runtime/jason-ops.sh capture [minutes]

Commands:
  status           Show runtime/gateway/Ollama container state.
  deploy           Recover current live mount inputs, validate Compose, capture a rollback image,
                   rebuild only jason-runtime, redeploy it, and wait for health.
  baseline-deploy  Recreate the current runtime from the already-installed jason-runtime:local image
                   with dynamic conversation disabled. No image build is performed and the repository/local
                   Compose file is not modified.
  capture          Capture recent Teams gateway, Ollama, security-audit, and orchestration evidence.
                   Default window: 5 minutes.
EOF
}

container_exists() {
    docker inspect "$1" >/dev/null 2>&1
}

compose_runtime() {
    if [ -n "$JASON_COMPOSE_OVERRIDE_FILE" ]; then
        docker compose -f "$COMPOSE_FILE" -f "$JASON_COMPOSE_OVERRIDE_FILE" "$@"
    else
        docker compose -f "$COMPOSE_FILE" "$@"
    fi
}

status() {
    echo "========== JASON STATUS =========="
    for container in "$RUNTIME_CONTAINER" "$GATEWAY_CONTAINER" "$OLLAMA_CONTAINER"; do
        if container_exists "$container"; then
            state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null)"
            image="$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null)"
            echo "$container | state=$state | image=$image"
        else
            echo "$container | state=missing"
        fi
    done
    echo "========== END =========="
}

recover_live_inputs() {
    eval "$(
        docker inspect "$RUNTIME_CONTAINER" | python3 -c '
import json
import shlex
import sys

data = json.load(sys.stdin)[0]
mounts = {item["Destination"]: item["Source"] for item in data.get("Mounts", [])}
required = {
    "JASON_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/role_id",
    "JASON_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/secret_id",
    "JASON_SES_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/aws-ses/role_id",
    "JASON_SES_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/aws-ses/secret_id",
    "JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/microsoft-graph/role_id",
    "JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/microsoft-graph/secret_id",
    "JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH": "/run/jason-secrets/openbao/openai/role_id",
    "JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH": "/run/jason-secrets/openbao/openai/secret_id",
}
for variable, destination in required.items():
    source = mounts.get(destination)
    if source:
        print("export " + variable + "=" + shlex.quote(source))

env = {}
for entry in data.get("Config", {}).get("Env", []):
    if "=" in entry:
        key, value = entry.split("=", 1)
        env[key] = value
model = env.get("JASON_OLLAMA_MODEL", "").strip()
if model:
    print("export JASON_OLLAMA_MODEL=" + shlex.quote(model))
'
    )"
}

validate_live_inputs() {
    required_names="
JASON_OPENBAO_ROLE_ID_HOST_PATH
JASON_OPENBAO_SECRET_ID_HOST_PATH
JASON_SES_OPENBAO_ROLE_ID_HOST_PATH
JASON_SES_OPENBAO_SECRET_ID_HOST_PATH
JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH
JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH
JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH
JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH
JASON_OLLAMA_MODEL
"

    input_rc=0
    for name in $required_names; do
        eval "value=\${$name:-}"
        if [ -n "$value" ]; then
            echo "$name=SET"
        else
            echo "$name=MISSING"
            input_rc=1
        fi
    done
    return "$input_rc"
}

wait_for_runtime_health() {
    health_rc=1
    attempt=1
    while [ "$attempt" -le 30 ]; do
        state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$RUNTIME_CONTAINER" 2>/dev/null)"
        echo "HEALTH_ATTEMPT=$attempt STATE=$state"
        if [ "$state" = "healthy" ]; then
            health_rc=0
            break
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return "$health_rc"
}

build_runtime_image() {
    attempt=1
    while [ "$attempt" -le 2 ]; do
        echo "BUILD_ATTEMPT=$attempt"
        if compose_runtime build jason-runtime; then
            return 0
        fi
        if [ "$attempt" -lt 2 ]; then
            echo "BUILD_RETRY=1"
            echo "REASON=runtime build/export failed; retrying once without changing source or pruning Docker state"
            sleep 2
        fi
        attempt=$((attempt + 1))
    done
    return 1
}

deploy() {
    echo "========== JASON RUNTIME DEPLOY =========="

    if ! container_exists "$RUNTIME_CONTAINER"; then
        echo "DEPLOY_RESULT=FAIL"
        echo "REASON=jason-runtime container not found"
        return 1
    fi

    recover_live_inputs
    if ! validate_live_inputs; then
        echo "DEPLOY_RESULT=FAIL"
        echo "REASON=required live deployment input missing"
        return 1
    fi

    if ! compose_runtime config --quiet; then
        echo "DEPLOY_RESULT=FAIL"
        echo "REASON=compose validation failed"
        return 1
    fi
    echo "COMPOSE_VALIDATION=PASS"

    old_image_id="$(docker inspect --format '{{.Image}}' "$RUNTIME_CONTAINER" 2>/dev/null)"
    rollback_tag=""
    if [ -n "$old_image_id" ]; then
        rollback_tag="jason-runtime:rollback-$(date +%Y%m%d-%H%M%S)"
        docker image tag "$old_image_id" "$rollback_tag"
        echo "ROLLBACK_IMAGE=$rollback_tag"
    fi

    if ! build_runtime_image; then
        echo "DEPLOY_RESULT=FAIL"
        echo "REASON=runtime build failed after bounded retry"
        return 1
    fi

    if ! compose_runtime up -d --no-deps --force-recreate jason-runtime; then
        echo "DEPLOY_RESULT=FAIL"
        echo "REASON=runtime deployment failed"
        [ -n "$rollback_tag" ] && echo "ROLLBACK_IMAGE=$rollback_tag"
        return 1
    fi

    if wait_for_runtime_health; then
        echo "DEPLOY_RESULT=PASS"
        echo "READY_FOR_LIVE_TEST=1"
        return 0
    fi

    echo "DEPLOY_RESULT=FAIL"
    echo "READY_FOR_LIVE_TEST=0"
    [ -n "$rollback_tag" ] && echo "ROLLBACK_IMAGE=$rollback_tag"
    return 1
}

baseline_deploy() {
    echo "========== JASON TEAMS WORKING BASELINE =========="

    if ! container_exists "$RUNTIME_CONTAINER"; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=jason-runtime container not found"
        return 1
    fi

    recover_live_inputs
    if ! validate_live_inputs; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=required live deployment input missing"
        return 1
    fi

    if ! docker image inspect jason-runtime:local >/dev/null 2>&1; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=existing jason-runtime:local image not found"
        return 1
    fi
    echo "BASELINE_IMAGE=jason-runtime:local"
    echo "BASELINE_BUILD=SKIPPED"

    override_file="$(mktemp)"
    cat > "$override_file" <<'EOF'
services:
  jason-runtime:
    environment:
      JASON_DYNAMIC_CONVERSATION_ENABLED: "false"
EOF
    JASON_COMPOSE_OVERRIDE_FILE="$override_file"

    if ! compose_runtime config --quiet; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=baseline compose validation failed"
        rm -f "$override_file"
        JASON_COMPOSE_OVERRIDE_FILE=""
        return 1
    fi
    echo "COMPOSE_VALIDATION=PASS"

    old_image_id="$(docker inspect --format '{{.Image}}' "$RUNTIME_CONTAINER" 2>/dev/null)"
    rollback_tag=""
    if [ -n "$old_image_id" ]; then
        rollback_tag="jason-runtime:rollback-$(date +%Y%m%d-%H%M%S)"
        docker image tag "$old_image_id" "$rollback_tag"
        echo "ROLLBACK_IMAGE=$rollback_tag"
    fi

    if ! compose_runtime up -d --no-build --no-deps --force-recreate jason-runtime; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=baseline runtime recreation failed"
        [ -n "$rollback_tag" ] && echo "ROLLBACK_IMAGE=$rollback_tag"
        rm -f "$override_file"
        JASON_COMPOSE_OVERRIDE_FILE=""
        return 1
    fi

    baseline_rc=0
    if ! wait_for_runtime_health; then
        echo "BASELINE_MODE=FAIL"
        echo "REASON=baseline runtime did not become healthy"
        [ -n "$rollback_tag" ] && echo "ROLLBACK_IMAGE=$rollback_tag"
        baseline_rc=1
    else
        dynamic_value="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$RUNTIME_CONTAINER" 2>/dev/null | grep '^JASON_DYNAMIC_CONVERSATION_ENABLED=' | tail -n 1 | cut -d= -f2-)"
        if [ "${dynamic_value:-false}" = "false" ]; then
            echo "BASELINE_MODE=PASS"
            echo "JASON_DYNAMIC_CONVERSATION_ENABLED=false"
            echo "READY_FOR_LIVE_TEST=1"
        else
            echo "BASELINE_MODE=FAIL"
            echo "REASON=runtime did not start with dynamic conversation disabled"
            baseline_rc=1
        fi
    fi

    rm -f "$override_file"
    JASON_COMPOSE_OVERRIDE_FILE=""
    return "$baseline_rc"
}

capture() {
    minutes="${1:-5}"
    case "$minutes" in
        ''|*[!0-9]*)
            echo "capture minutes must be a positive integer"
            return 2
            ;;
    esac
    if [ "$minutes" -lt 1 ]; then
        echo "capture minutes must be at least 1"
        return 2
    fi

    since="${minutes}m"
    echo "========== JASON LIVE CAPTURE =========="
    echo "WINDOW_MINUTES=$minutes"

    echo
    echo "========== GATEWAY =========="
    if container_exists "$GATEWAY_CONTAINER"; then
        docker logs --since "$since" --timestamps "$GATEWAY_CONTAINER" 2>&1 \
            | grep -E 'jason_teams_runtime_failure|jason_teams_turn_completed' \
            | tail -n 40 || true
    else
        echo "GATEWAY_CONTAINER=MISSING"
    fi

    echo
    echo "========== OLLAMA =========="
    if container_exists "$OLLAMA_CONTAINER"; then
        docker logs --since "$since" --timestamps "$OLLAMA_CONTAINER" 2>&1 \
            | grep -E 'new prompt|prompt processing|n_decoded|POST.*"/api/chat"|cancel task|stop processing' \
            | tail -n 120 || true
    else
        echo "OLLAMA_CONTAINER=MISSING"
    fi

    echo
    echo "========== CONVERSATION AUDIT =========="
    if container_exists "$RUNTIME_CONTAINER"; then
        docker exec -i "$RUNTIME_CONTAINER" python - "$minutes" <<'PY'
import json
import sqlite3
import sys

minutes = int(sys.argv[1])
conn = sqlite3.connect(
    "file:/var/lib/jason/openclaw/security-audit.sqlite3?mode=ro",
    uri=True,
)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT *
    FROM openclaw_ingress_security_events
    WHERE occurred_at >= datetime('now', ?)
    ORDER BY occurred_at
    """,
    (f"-{minutes} minutes",),
).fetchall()
print(f"SECURITY_EVENT_COUNT={len(rows)}")
for row in rows:
    print()
    print(f"EVENT_TYPE={row['event_type']}")
    if 'request_id' in row.keys():
        print(f"REQUEST_ID={row['request_id']}")
    if 'correlation_id' in row.keys():
        print(f"CORRELATION_ID={row['correlation_id']}")
    print(f"OCCURRED_AT={row['occurred_at']}")

    payload = {}
    for candidate in ("payload", "details", "event_data"):
        if candidate in row.keys() and row[candidate]:
            try:
                payload = json.loads(row[candidate])
                break
            except Exception:
                pass
    for key in (
        "reason_code",
        "error_type",
        "error_message",
        "orchestration_status",
        "response_status",
    ):
        value = payload.get(key)
        if value is not None:
            print(f"{key.upper()}={str(value)[:1000]}")
conn.close()
PY
    else
        echo "RUNTIME_CONTAINER=MISSING"
    fi

    echo
    echo "========== ORCHESTRATION =========="
    if container_exists "$RUNTIME_CONTAINER"; then
        docker exec -i "$RUNTIME_CONTAINER" python - "$minutes" <<'PY'
import sqlite3
import sys

minutes = int(sys.argv[1])
conn = sqlite3.connect(
    "file:/var/lib/jason/openclaw/orchestration-events.sqlite3?mode=ro",
    uri=True,
)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT *
    FROM orchestration_events
    WHERE occurred_at >= datetime('now', ?)
    ORDER BY occurred_at, event_id
    """,
    (f"-{minutes} minutes",),
).fetchall()
print(f"ORCHESTRATION_EVENT_COUNT={len(rows)}")
for row in rows:
    values = []
    for key in (
        "occurred_at",
        "event_type",
        "capability_name",
        "stage",
        "correlation_id",
    ):
        if key in row.keys():
            values.append(str(row[key]))
    print(" | ".join(values))
conn.close()
PY
    else
        echo "RUNTIME_CONTAINER=MISSING"
    fi

    echo
    echo "========== END =========="
}

command="${1:-}"
case "$command" in
    status)
        status
        ;;
    deploy)
        deploy
        ;;
    baseline-deploy)
        baseline_deploy
        ;;
    capture)
        capture "${2:-5}"
        ;;
    -h|--help|help|'')
        usage
        ;;
    *)
        echo "Unknown command: $command"
        usage
        return 2 2>/dev/null || exit 2
        ;;
esac
