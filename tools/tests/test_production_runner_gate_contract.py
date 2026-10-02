from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_production_deploy_requires_exact_plan_permit_before_helper():
    text = read("infrastructure/jason-runtime/production-deploy.sh")
    assert "JASON_PRODUCTION_PROMOTION_PERMIT" in text
    assert "JASON_PRODUCTION_PLAN_SHA256" in text
    assert '--promotion-component "jason-runtime"' in text
    assert "exit 42" in text
    gate = text.index("PRODUCTION_PROMOTION_GATE=FAIL")
    helper = text.index("tools/deploy_live_container.py")
    assert gate < helper


def test_mcp_production_deploy_requires_exact_plan_permit_before_helper():
    text = read("infrastructure/jason-mcp/production-deploy.sh")
    assert "JASON_PRODUCTION_PROMOTION_PERMIT" in text
    assert "JASON_PRODUCTION_PLAN_SHA256" in text
    assert '--promotion-component "jason-mcp"' in text
    assert "exit 42" in text
    gate = text.index("PRODUCTION_PROMOTION_GATE=FAIL")
    helper = text.index("tools/deploy_live_container.py")
    assert gate < helper


def test_generic_live_container_helper_claims_permit_before_first_docker_stop():
    text = read("tools/deploy_live_container.py")
    claim = text.index("permit = verify_and_claim_production_permit")
    stop = text.index('_run(["docker", "stop", args.live]')
    assert claim < stop
    assert 'raise SystemExit("Production mutation requires --production-permit")' in text


def test_teams_cutover_uses_prebuilt_candidate_and_claims_before_mutation():
    text = read("infrastructure/jason-teams-gateway/cutover-production.sh")
    assert "docker build" not in text
    assert "immutable candidate image is not present" in text
    claim = text.index("claim_production_promotion_permit.py")
    first_live_write = text.index('sudo install -m 0644 "$LOCAL_NEXT_COMPOSE" "$NEXT_COMPOSE"')
    compose_apply = text.index('docker compose -p "$OPENCLAW_PROJECT" -f "$OPENCLAW_COMPOSE_FILE" up -d', claim)
    assert claim < first_live_write
    assert claim < compose_apply
    assert '--component jason-teams-gateway' in text
    assert '--operation deploy' in text


def test_teams_cutover_preflight_exits_before_permit_claim():
    text = read("infrastructure/jason-teams-gateway/cutover-production.sh")
    preflight_exit = text.index('echo "CUTOVER_STATUS=PREFLIGHT_ONLY"')
    claim = text.index("claim_production_promotion_permit.py")
    assert preflight_exit < claim


def test_teams_standalone_rollback_requires_signed_rollback_permit_before_mutation():
    text = read("infrastructure/jason-teams-gateway/rollback-production.sh")
    assert "JASON_PRODUCTION_ROLLBACK_PERMIT" in text
    assert "JASON_PRODUCTION_PLAN_SHA256" in text
    assert '--operation rollback' in text
    claim = text.index("claim_production_promotion_permit.py")
    mutation = text.index('docker rm -f "$GATEWAY_CONTAINER"')
    assert claim < mutation
    assert "compose backup digest does not match cutover state" in text


def test_autonomous_repair_policy_cannot_self_promote_to_production():
    import json
    policy = json.loads(read("config/autonomous-repair-release-policy.json"))
    assert policy["automatic_production_execution_enabled"] is False


def test_baseline_refresh_cannot_build_or_retag_before_production_gate():
    text = read("infrastructure/jason-runtime/jason-baseline-refresh.sh")
    assert "docker build" not in text
    assert "docker buildx" not in text
    assert "docker tag" not in text
    assert "JASON_RUNTIME_CANDIDATE_IMAGE is required" in text
    permit_check = text.index("exact-plan Production permit and plan digest are required")
    deploy = text.index("infrastructure/jason-runtime/production-deploy.sh")
    assert permit_check < deploy


def test_jason_ops_deploy_routes_through_gated_baseline_wrapper():
    text = read("infrastructure/jason-runtime/jason-ops.sh")
    deploy_fn = text.index("deploy()")
    baseline = text.index("jason-baseline-refresh.sh", deploy_fn)
    assert baseline > deploy_fn
