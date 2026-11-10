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


def test_build_create_command_adds_source_revision_when_live_env_missing(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    live = _live(existing)
    live["Config"]["Env"] = ["JASON_OPENBAO_URL=http://openbao:8200"]
    monkeypatch.setattr(deploy, "_inspect", lambda name: live)

    command, env_map, _, _ = deploy._build_create_command(
        live="jason-runtime",
        image="jason-runtime:test",
        source_revision="exact-new-revision",
        harden=True,
    )

    assert env_map["JASON_SOURCE_REVISION"] == "exact-new-revision"
    assert "--env" in command
    assert "JASON_SOURCE_REVISION" in command


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


def test_protected_readonly_bind_uses_docker_probe_when_host_path_is_not_visible(
    monkeypatch, tmp_path: Path
) -> None:
    existing = tmp_path / "existing"
    existing.write_text("existing")
    monkeypatch.setattr(deploy, "_inspect", lambda name: _live(existing))

    protected = "/opt/jason/protected/role-id"
    real_exists = deploy.os.path.exists
    monkeypatch.setattr(
        deploy.os.path,
        "exists",
        lambda path: False if str(path) == protected else real_exists(path),
    )

    calls = []

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)

    command, _, _, _ = deploy._build_create_command(
        live="jason-mcp-pilot",
        image="jason-mcp:test",
        source_revision="new-revision",
        harden=True,
        additional_readonly_binds=(
            f"{protected}:/run/protected/role_id",
        ),
    )

    assert calls
    assert calls[0][0:3] == ["docker", "run", "--rm"]
    assert (
        f"type=bind,src={protected},dst=/run/protected/role_id,readonly"
        in command
    )


def test_health_defaults_to_existing_python_http_probe(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(deploy.subprocess,"run",lambda cmd,**kw:(calls.append(cmd) or SimpleNamespace(returncode=0)))
    deploy._health("jason-runtime","http://127.0.0.1:8080/healthz",1,0)
    assert calls[0][:5]==["docker","exec","jason-runtime","python","-c"]
    assert "r.status == 200" in calls[0][-1]


def test_node_gateway_health_requires_same_http_200_and_timeout(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(deploy.subprocess,"run",lambda cmd,**kw:(calls.append(cmd) or SimpleNamespace(returncode=0)))
    deploy._health("jason-teams-gateway","http://127.0.0.1:3979/healthz",1,0,"node")
    assert calls[0][:5]==["docker","exec","jason-teams-gateway","node","-e"]
    assert "r.status !== 200" in calls[0][-1]
    assert "AbortSignal.timeout(3000)" in calls[0][-1]
    assert "python" not in calls[0]


def test_node_gateway_unhealthy_fails_after_bounded_attempts(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(deploy.subprocess,"run",lambda cmd,**kw:(calls.append(cmd) or SimpleNamespace(returncode=1)))
    monkeypatch.setattr(deploy.time,"sleep",lambda value:None)
    with pytest.raises(RuntimeError,match="health verification"):
        deploy._health("jason-teams-gateway","http://127.0.0.1:3979/healthz",2,0,"node")
    assert len(calls)==2


def test_unknown_health_runtime_refuses_without_execution(monkeypatch):
    calls=[]
    monkeypatch.setattr(deploy.subprocess,"run",lambda cmd,**kw:calls.append(cmd))
    with pytest.raises(ValueError,match="unsupported"):
        deploy._health("jason-teams-gateway","http://127.0.0.1:3979/healthz",1,0,"shell")
    assert calls==[]


def test_owner_private_signer_bind_is_readonly_and_removed_from_v2_rollback(
    monkeypatch, tmp_path: Path,
) -> None:
    prior = tmp_path / "existing"
    prior.write_text("ordinary existing bind")
    signer = tmp_path / "private_key"
    signer.write_bytes(b"x" * 32)
    current = _live(prior)
    current["Mounts"].append({
        "Type": "bind",
        "Source": str(signer),
        "Destination": "/run/jason-secrets/owner-release/private_key",
        "RW": False,
    })
    monkeypatch.setattr(deploy, "_inspect", lambda name: current)
    command, _, _, _ = deploy._build_create_command(
        live="jason-mcp-pilot",
        image="jason-mcp:rollback-current",
        source_revision="v2",
        harden=True,
        set_env=("JASON_OWNER_RELEASE_ED25519_KEY_PATH=",),
        omit_readonly_bind_destinations=(
            "/run/jason-secrets/owner-release/private_key",
        ),
    )
    assert f"type=bind,src={prior},dst=/run/existing,readonly" in command
    assert not any(str(signer) in part for part in command)
    assert not any("/owner-release/private_key" in part for part in command)


def test_cannot_omit_owner_signer_if_mount_is_writable(monkeypatch, tmp_path):
    prior = tmp_path / "existing"
    prior.write_text("data")
    current = _live(prior)
    current["Mounts"].append({
        "Type": "bind",
        "Source": str(prior),
        "Destination": "/run/jason-secrets/owner-release/private_key",
        "RW": True,
    })
    monkeypatch.setattr(deploy, "_inspect", lambda name: current)
    with pytest.raises(ValueError, match="cannot omit writable"):
        deploy._build_create_command(
            live="jason-mcp-pilot",
            image="jason-mcp:rollback-current",
            source_revision="v2",
            harden=True,
            omit_readonly_bind_destinations=(
                "/run/jason-secrets/owner-release/private_key",
            ),
        )


@pytest.mark.parametrize("live,image,env", [
    ("jason-runtime", "jason-mcp:rollback-current",
     ["JASON_OWNER_RELEASE_ED25519_KEY_PATH="]),
    ("jason-mcp-pilot", "jason-mcp:production",
     ["JASON_OWNER_RELEASE_ED25519_KEY_PATH="]),
    ("jason-mcp-pilot", "jason-mcp:rollback-current", []),
])
def test_secret_mount_can_only_be_omitted_for_exact_unprivileged_mcp_rollback(
    monkeypatch, live, image, env,
):
    import sys

    cmd = [
        "deploy_live_container.py",
        "--live", live, "--image", image,
        "--rollback", "some-rollback-container",
        "--source-revision", "b" * 40,
        "--health-url", "http://127.0.0.1:8000/healthz",
        "--omit-owner-release-signer-bind-on-rollback",
    ]
    for item in env:
        cmd.extend(["--set-env", item])
    monkeypatch.setattr(sys, "argv", cmd)
    with pytest.raises(SystemExit) as error:
        deploy.main()
    assert error.value.code == 2


def test_native_mcp_source_requires_immutable_signer_and_root_trust():
    source = (
        Path(__file__).resolve().parents[2]
        / "infrastructure/jason-mcp/production-deploy.sh"
    ).read_text()
    assert 'OWNER_SIGNER_HOST="/var/lib/jason/runtime-secrets/owner-release/private_key"' in source
    assert 'OWNER_SIGNER_PUBLIC_POLICY="/etc/jason/owner-release/verified-owner-public-key.json"' in source
    assert 'OWNER_SIGNER_OWNER_MODE' in source
    assert 'MCP_OWNER_SIGNER_ROOT_TRUST_PRECHECK=PASS' in source
    assert 'MCP_OWNER_RELEASE_SIGNER_MOUNT=PASS' in source
    assert '--omit-owner-release-signer-bind-on-rollback' in source
    assert '--add-readonly-bind "$OWNER_SIGNER_HOST:$OWNER_SIGNER_CONTAINER"' in source
    assert 'JASON_OWNER_RELEASE_ED25519_KEY_PATH=' in source
    assert "read_service_owner_signing_key" in source
    assert "read_pinned_root_owner_public_key" in source
