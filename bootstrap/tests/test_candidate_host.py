from __future__ import annotations

import json
from pathlib import Path

import pytest

from bootstrap.candidate_host import (
    CandidateHostAuthorizationError,
    CandidateHostIdentity,
    authorize_mutation_target,
    load_candidate_host_identity,
)


def valid_identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def test_non_root_target_does_not_require_candidate_identity(tmp_path):
    assert authorize_mutation_target(
        target_root=tmp_path / "candidate",
        candidate_identity=None,
        operation="test",
    ) == tmp_path / "candidate"


def test_live_root_requires_explicit_candidate_identity():
    with pytest.raises(
        CandidateHostAuthorizationError,
        match="requires explicit candidate-host identity",
    ):
        authorize_mutation_target(
            target_root="/",
            candidate_identity=None,
            operation="bootstrap",
        )
    assert authorize_mutation_target(
        target_root="/",
        candidate_identity=valid_identity(),
        operation="bootstrap",
    ) == Path("/")


def test_production_identity_can_never_authorize_candidate_mutation():
    with pytest.raises(
        CandidateHostAuthorizationError,
        match="not candidate",
    ):
        authorize_mutation_target(
            target_root="/",
            candidate_identity=CandidateHostIdentity(
                schema_version="1.0",
                environment="production",
                instance_id="production",
                bootstrap_authorized=True,
            ),
            operation="bootstrap",
        )


def test_candidate_identity_file_is_fail_closed(tmp_path):
    path = tmp_path / "candidate-host.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "candidate",
                "instance_id": "jason-b",
                "bootstrap_authorized": True,
            }
        )
    )
    assert load_candidate_host_identity(path).instance_id == "jason-b"

    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "candidate",
                "instance_id": "jason-b",
                "bootstrap_authorized": False,
            }
        )
    )
    with pytest.raises(
        CandidateHostAuthorizationError,
        match="not authorized",
    ):
        load_candidate_host_identity(path)
