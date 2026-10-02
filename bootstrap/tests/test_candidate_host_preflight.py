from __future__ import annotations

import json
from pathlib import Path

from bootstrap.candidate_host_preflight import preflight_candidate_host
from bootstrap.clean_install import HostObservation


def host():
    return HostObservation(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker version 29",
        compose_version="Docker Compose version 5",
    )


def identity(tmp_path: Path):
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
    path.chmod(0o640)
    return path


def test_blank_supported_root_is_ready_for_host_install(tmp_path):
    root = tmp_path / "blank-root"
    root.mkdir()
    result = preflight_candidate_host(
        root=root,
        identity_path=identity(tmp_path),
        host=host(),
        effective_uid=0,
    )
    assert result.status == "ready_for_host_install"
    assert result.clean_host is True
    assert result.blockers == ()


def test_prior_jason_state_blocks_blank_host_acceptance(tmp_path):
    root = tmp_path / "not-blank"
    marker = root / "var/lib/jason/deployment-manifest.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}")
    result = preflight_candidate_host(
        root=root,
        identity_path=identity(tmp_path),
        host=host(),
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert (
        "prior_jason_state:var/lib/jason/deployment-manifest.json"
        in result.blockers
    )
    assert result.clean_host is False


def test_non_root_and_bad_identity_permissions_block(tmp_path):
    root = tmp_path / "blank-root"
    root.mkdir()
    ident = identity(tmp_path)
    ident.chmod(0o666)
    result = preflight_candidate_host(
        root=root,
        identity_path=ident,
        host=host(),
        effective_uid=1000,
    )
    assert result.status == "blocked"
    assert "root_privileges_required" in result.blockers
    assert "candidate_identity_permissions_invalid" in result.blockers


def test_unsupported_host_blocks(tmp_path):
    root = tmp_path / "blank-root"
    root.mkdir()
    bad = HostObservation(
        os_id="debian",
        os_version="13",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker",
        compose_version="Compose",
    )
    result = preflight_candidate_host(
        root=root,
        identity_path=identity(tmp_path),
        host=bad,
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert any(
        item.startswith("host_prerequisite:unsupported OS")
        for item in result.blockers
    )
