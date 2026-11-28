"""One shared provider canary bootstrap; never multiply AppRole failures."""
import json

from jason_mcp import provider_health_canary as canary


def test_shared_runtime_bootstrap_failure_makes_only_one_auth_attempt(monkeypatch):
    attempts = []

    def failed_authentication():
        attempts.append("attempt")
        raise RuntimeError("PRIVATE_APPROLE_CREDENTIAL_MUST_NOT_LEAK")

    monkeypatch.setattr(canary.server, "_runtime", failed_authentication)
    result = canary.run_canaries()

    assert attempts == ["attempt"]
    assert result["schema_version"] == 1
    assert len(result["results"]) == len(canary.PROVIDER_HEALTH_CANARY_SPECS) == 4
    assert all(entry["healthy"] is False for entry in result["results"])
    assert all(entry["error_class"] == "runner_error" for entry in result["results"])
    assert all(entry["latency_seconds"] == 0.0 for entry in result["results"])
    assert all(entry["correlation_id"].startswith("corr_") for entry in result["results"])
    assert "PRIVATE_APPROLE_CREDENTIAL" not in json.dumps(result)


def test_successful_shared_bootstrap_executes_all_four_with_single_runtime(monkeypatch):
    application = object()
    attempts = []
    used = []

    def bootstrap():
        attempts.append("attempt")
        return application

    def execute(spec, *, app):
        assert app is application
        used.append(spec["provider_id"])
        return {
            "provider": spec["provider_id"],
            "capability": spec["capability_name"],
            "healthy": True,
            "latency_seconds": 0.125,
            "error_class": "none",
            "correlation_id": "corr_test_safe",
        }

    monkeypatch.setattr(canary.server, "_runtime", bootstrap)
    monkeypatch.setattr(canary, "_run_one", execute)
    result = canary.run_canaries()
    assert attempts == ["attempt"]
    assert used == [spec["provider_id"] for spec in canary.PROVIDER_HEALTH_CANARY_SPECS]
    assert len(result["results"]) == 4
    assert all(entry["healthy"] for entry in result["results"])


def test_one_provider_failure_does_not_retry_shared_bootstrap_or_mask_others(monkeypatch):
    app = object()
    bootstrap_count = []
    bad = canary.PROVIDER_HEALTH_CANARY_SPECS[1]["provider_id"]

    def bootstrap():
        bootstrap_count.append(1)
        return app

    def execute(spec, *, app):
        assert app is not None
        if spec["provider_id"] == bad:
            raise RuntimeError("PRIVATE_BAD_PROVIDER_DATA")
        return {
            "provider": spec["provider_id"],
            "capability": spec["capability_name"],
            "healthy": True,
            "latency_seconds": 0.05,
            "error_class": "none",
            "correlation_id": "corr_test_safe",
        }

    monkeypatch.setattr(canary.server, "_runtime", bootstrap)
    monkeypatch.setattr(canary, "_run_one", execute)
    result = canary.run_canaries()
    assert bootstrap_count == [1]
    assert len(result["results"]) == 4
    failing = [entry for entry in result["results"] if not entry["healthy"]]
    assert len(failing) == 1 and failing[0]["provider"] == bad
    assert failing[0]["error_class"] == "runner_error"
    assert "PRIVATE_BAD_PROVIDER_DATA" not in json.dumps(result)
