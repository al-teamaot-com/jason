from __future__ import annotations

import json
from pathlib import Path

import pytest

from bootstrap.clean_install import (
    HostObservation,
    apply_layout,
    build_plan,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "config" / "schemas"
EXAMPLES = ROOT / "config" / "examples"


def good_host() -> HostObservation:
    return HostObservation(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker version 29.6.2",
        compose_version="Docker Compose version v5.3.1",
    )


def test_candidate_plan_is_deterministic_and_contains_no_secret_values(tmp_path):
    first = build_plan(
        environment="candidate",
        target_root=tmp_path / "jason-a",
        msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
        msp_policy_path=EXAMPLES / "msp-policy.example.json",
        schema_root=SCHEMAS,
        host=good_host(),
    )
    second = build_plan(
        environment="candidate",
        target_root=tmp_path / "jason-a",
        msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
        msp_policy_path=EXAMPLES / "msp-policy.example.json",
        schema_root=SCHEMAS,
        host=good_host(),
    )
    assert first == second
    from dataclasses import asdict
    encoded = json.dumps(asdict(first))
    assert "autotask.readonly" not in encoded


def test_production_target_is_refused(tmp_path):
    with pytest.raises(PermissionError, match="non-production only"):
        build_plan(
            environment="production",
            target_root=tmp_path / "jason-prod",
            msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
            msp_policy_path=EXAMPLES / "msp-policy.example.json",
            schema_root=SCHEMAS,
            host=good_host(),
        )


def test_live_filesystem_root_is_refused():
    with pytest.raises(PermissionError, match="live filesystem root"):
        build_plan(
            environment="candidate",
            target_root="/",
            msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
            msp_policy_path=EXAMPLES / "msp-policy.example.json",
            schema_root=SCHEMAS,
            host=good_host(),
        )


def test_layout_apply_creates_only_target_root_and_identity(tmp_path):
    root = tmp_path / "candidate-root"
    plan = build_plan(
        environment="candidate",
        target_root=root,
        msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
        msp_policy_path=EXAMPLES / "msp-policy.example.json",
        schema_root=SCHEMAS,
        host=good_host(),
    )
    identity = apply_layout(plan)
    assert identity == root / "var/lib/jason/deployment-bootstrap.json"
    assert identity.exists()
    assert (root / "opt/jason/releases").is_dir()
    assert (root / "var/lib/jason/authority").is_dir()


def test_unsupported_host_fails_before_layout(tmp_path):
    bad = HostObservation(
        os_id="ubuntu",
        os_version="22.04",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker version 29",
        compose_version="Docker Compose version 5",
    )
    with pytest.raises(ValueError, match="unsupported Ubuntu"):
        build_plan(
            environment="candidate",
            target_root=tmp_path / "bad",
            msp_configuration_path=EXAMPLES / "msp-configuration.example.json",
            msp_policy_path=EXAMPLES / "msp-policy.example.json",
            schema_root=SCHEMAS,
            host=bad,
        )
