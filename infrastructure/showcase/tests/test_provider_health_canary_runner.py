import importlib.util
from pathlib import Path

import pytest


def load_runner():
    path = Path(__file__).resolve().parents[1] / "run_provider_health_canaries.py"
    spec = importlib.util.spec_from_file_location("provider_health_canary_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_payload():
    return {
        "schema_version": 1,
        "generated_at": "2026-09-27T16:00:00+00:00",
        "generated_at_epoch": 1.0,
        "principal": "jason-provider-canary",
        "policy": "provider-health-canary-v1",
        "results": [
            {
                "provider": "autotask",
                "capability": "service.company.search",
                "healthy": True,
                "latency_seconds": 0.4,
                "error_class": "none",
                "correlation_id": "corr_provider_canary_test",
            }
        ],
    }


def test_validate_accepts_bounded_secret_safe_payload():
    module = load_runner()
    assert module._validate(valid_payload())["schema_version"] == 1


def test_validate_rejects_unbounded_error_class():
    module = load_runner()
    payload = valid_payload()
    payload["results"][0]["error_class"] = "raw_exception_with_secret"
    with pytest.raises(ValueError, match="error class"):
        module._validate(payload)


def test_validate_rejects_unknown_provider():
    module = load_runner()
    payload = valid_payload()
    payload["results"][0]["provider"] = "unknown"
    with pytest.raises(ValueError, match="unexpected provider"):
        module._validate(payload)
