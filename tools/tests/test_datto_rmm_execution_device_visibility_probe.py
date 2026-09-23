from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "datto_rmm_execution_device_visibility_probe.py"
SPEC = importlib.util.spec_from_file_location("datto_execution_device_visibility", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_assessment_requires_positive_and_negative_visibility():
    result = MODULE.assess_device_visibility(
        [
            {
                "label": "visible-device",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 200,
            },
            {
                "label": "hidden-device",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 403,
            },
        ]
    )
    assert result["status"] == "pass"
    assert result["device_visibility_proven"] is True
    assert result["positive_visibility_proven"] is True
    assert result["negative_visibility_proven"] is True


def test_assessment_accepts_404_as_hidden_only_with_visible_site():
    result = MODULE.assess_device_visibility(
        [
            {
                "label": "visible-device",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 200,
            },
            {
                "label": "hidden-device",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 404,
            },
        ]
    )
    assert result["status"] == "pass"
    assert result["hidden_candidate_count"] == 1


def test_assessment_does_not_treat_site_denial_as_device_visibility_proof():
    result = MODULE.assess_device_visibility(
        [
            {
                "label": "visible-device",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 200,
            },
            {
                "label": "unknown-boundary",
                "readonly_resolution": "unique",
                "execution_site_http": 403,
                "execution_device_http": 403,
            },
        ]
    )
    assert result["status"] == "inconclusive"
    assert result["negative_visibility_proven"] is False
    assert result["unexpected_candidate_count"] == 1


def test_assessment_rejects_only_visible_candidates_as_inconclusive():
    result = MODULE.assess_device_visibility(
        [
            {
                "label": "device-one",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 200,
            },
            {
                "label": "device-two",
                "readonly_resolution": "unique",
                "execution_site_http": 200,
                "execution_device_http": 200,
            },
        ]
    )
    assert result["status"] == "inconclusive"
    assert result["positive_visibility_proven"] is True
    assert result["negative_visibility_proven"] is False


def test_preflight_is_network_and_mutation_free():
    result = MODULE.preflight(["device-one", "device-two"])
    assert result["status"] == "credential_safe_preflight"
    assert result["network_contacted"] is False
    assert result["provider_credentials_used"] is False
    assert result["provider_mutation_requests"] == 0
    assert result["component_execution_attempted"] is False
    assert result["runtime_execution_activated"] is False
    assert result["provider_ids_printed"] is False
    assert result["provider_response_bodies_printed"] is False
    assert result["provider_response_bodies_persisted"] is False
