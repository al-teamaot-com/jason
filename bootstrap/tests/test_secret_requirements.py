from __future__ import annotations

import json
from pathlib import Path

import pytest

from bootstrap.secret_requirements import (
    SecretRequirementError,
    build_secret_requirements,
    evaluate_secret_readiness,
    load_secret_presence_attestation,
    write_secret_requirements,
)


ROOT = Path(__file__).resolve().parents[2]


def config():
    return json.loads(
        (ROOT / "config/examples/msp-configuration.example.json").read_text()
    )


def test_enabled_providers_produce_logical_secret_requirements_only():
    requirements = build_secret_requirements(config())
    assert {
        (item.provider_id, item.secret_reference)
        for item in requirements
    } == {
        ("autotask", "autotask.readonly"),
        ("datto_rmm", "datto_rmm.readonly"),
    }


def test_disabled_provider_is_not_a_secret_requirement():
    payload = config()
    payload["providers"]["datto_rmm"]["enabled"] = False
    requirements = build_secret_requirements(payload)
    assert [item.provider_id for item in requirements] == ["autotask"]


def test_enabled_provider_without_reference_fails_closed():
    payload = config()
    payload["providers"]["autotask"]["secret_reference"] = None
    with pytest.raises(SecretRequirementError, match="no governed secret reference"):
        build_secret_requirements(payload)


def test_secret_reference_cannot_be_path_or_secret_value():
    payload = config()
    payload["providers"]["autotask"]["secret_reference"] = "/home/al/secret"
    with pytest.raises(SecretRequirementError, match="logical identifier"):
        build_secret_requirements(payload)

    payload["providers"]["autotask"]["secret_reference"] = "token=actual-secret"
    with pytest.raises(SecretRequirementError, match="logical identifier"):
        build_secret_requirements(payload)


def test_secret_readiness_reports_missing_refs_without_values(tmp_path):
    requirements = build_secret_requirements(config())
    path = write_secret_requirements(
        target_root=tmp_path / "candidate",
        requirements=requirements,
    )
    encoded = path.read_text()
    assert "autotask.readonly" in encoded
    assert '"contains_secret_values": false' in encoded

    readiness = evaluate_secret_readiness(
        requirements=requirements,
        available_references=("autotask.readonly",),
    )
    assert readiness["status"] == "blocked"
    assert readiness["missing_references"] == ["datto_rmm.readonly"]
    assert readiness["secret_values_observed"] is False

    ready = evaluate_secret_readiness(
        requirements=requirements,
        available_references=("autotask.readonly", "datto_rmm.readonly"),
    )
    assert ready["status"] == "ready"


def test_presence_attestation_rejects_secret_values(tmp_path):
    path = tmp_path / "attestation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contains_secret_values": True,
                "available_references": ["autotask.readonly"],
            }
        )
    )
    with pytest.raises(SecretRequirementError, match="no secret values"):
        load_secret_presence_attestation(path)
