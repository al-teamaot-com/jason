from __future__ import annotations

from pathlib import Path

import pytest

from tools import deploy_live_container as deploy


def _live(source: Path) -> dict:
    return {
        "Config": {
            "Env": [
                "JASON_SOURCE_REVISION=old",
                "JASON_OPENBAO_URL=http://openbao:8200",
            ],
            "User": "1000:1000",
            "WorkingDir": "/opt/jason-src",
            "Labels": {},
            "Healthcheck": None,
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "no"},
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=32m"},
            "PortBindings": {},
            "NetworkMode": "jason-core",
            "LogConfig": {"Type": "json-file", "Config": {}},
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(source),
                "Destination": "/run/existing",
                "RW": False,
            }
        ],
        "NetworkSettings": {"Networks": {"jason-core": {}}},
    }


def test_build_create_command_adds_nonsecret_env_and_readonly_bind(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    role = tmp_path / "role-id"
    role.write_text("role")

    monkeypatch.setattr(deploy, "_inspect", lambda name: _live(existing))

    command, env_map, secondary, _ = deploy._build_create_command(
        live="jason-mcp-pilot",
        image="jason-mcp:test",
        source_revision="new-revision",
        harden=True,
        set_env=(
            "JASON_BACKUP_NET_ENABLED=true",
            "JASON_BACKUP_NET_OPENBAO_ROLE_ID_PATH=/run/backup/role_id",
        ),
        additional_readonly_binds=(
            f"{role}:/run/backup/role_id",
        ),
    )

    assert env_map["JASON_SOURCE_REVISION"] == "new-revision"
    assert env_map["JASON_BACKUP_NET_ENABLED"] == "true"
    assert env_map["JASON_BACKUP_NET_OPENBAO_ROLE_ID_PATH"] == (
        "/run/backup/role_id"
    )
    assert secondary == []
    assert "JASON_BACKUP_NET_ENABLED" in command
    assert (
        f"type=bind,src={role},dst=/run/backup/role_id,readonly"
        in command
    )


def test_readonly_bind_is_idempotent_when_live_container_already_has_it(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    monkeypatch.setattr(deploy, "_inspect", lambda name: _live(existing))

    command, _, _, _ = deploy._build_create_command(
        live="jason-mcp-pilot",
        image="jason-mcp:test",
        source_revision="new-revision",
        harden=True,
        additional_readonly_binds=(f"{existing}:/run/existing",),
    )

    mount_spec = f"type=bind,src={existing},dst=/run/existing,readonly"
    assert command.count(mount_spec) == 1


def test_readonly_bind_rejects_destination_conflict(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    other = tmp_path / "other"
    other.write_text("other")
    monkeypatch.setattr(deploy, "_inspect", lambda name: _live(existing))

    with pytest.raises(ValueError, match="conflicts"):
        deploy._build_create_command(
            live="jason-mcp-pilot",
            image="jason-mcp:test",
            source_revision="new-revision",
            harden=True,
            additional_readonly_binds=(f"{other}:/run/existing",),
        )


def test_set_env_cannot_override_source_revision(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    monkeypatch.setattr(deploy, "_inspect", lambda name: _live(existing))

    with pytest.raises(ValueError, match="controlled"):
        deploy._build_create_command(
            live="jason-mcp-pilot",
            image="jason-mcp:test",
            source_revision="new-revision",
            harden=True,
            set_env=("JASON_SOURCE_REVISION=wrong",),
        )
