"""Exact-source group activation and credential-mount rollback contract tests."""
from pathlib import Path
import json
import sys
import pytest

from tools import deploy_live_container
from tools.microsoft_group_admin_release_profile import ALLOWED, read_profile

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/microsoft_graph/group-admin-release.json"
SCRIPT_RUNTIME = ROOT / "infrastructure/jason-runtime/production-deploy.sh"
SCRIPT_MCP = ROOT / "infrastructure/jason-mcp/production-deploy.sh"
DESTINATIONS = tuple(
    f"/run/jason-secrets/openbao/microsoft-group-{role}/{field}"
    for role in ("read", "write") for field in ("role_id", "secret_id")
)


def test_approved_source_profile_is_explicit_and_exact():
    assert read_profile(PROFILE) == ALLOWED["profile"]
    assert ALLOWED["client_id"] == "client-aot-internal"
    assert ALLOWED["tenant_id"] == "f7054323-d52b-4863-8c2f-1898f0b6077c"


@pytest.mark.parametrize("change", (
    {"client_id": "other-client"},
    {"tenant_id": "22222222-2222-4222-8222-222222222222"},
    {"profile": "other-profile"},
    {"unknown": "anything"},
))
def test_drifted_source_profile_fails_closed(tmp_path, change):
    profile = tmp_path / "profile.json"
    data = dict(ALLOWED)
    data.update(change)
    profile.write_text(json.dumps(data))
    with pytest.raises(PermissionError, match="NOT_APPROVED"):
        read_profile(profile)


def test_symlink_profile_refused(tmp_path):
    profile = tmp_path / "profile.json"
    profile.symlink_to(PROFILE)
    with pytest.raises(PermissionError, match="NOT_REGULAR"):
        read_profile(profile)


def test_release_scripts_mount_distinct_group_secrets_only_under_exact_source_activation():
    for script in (SCRIPT_RUNTIME, SCRIPT_MCP):
        text = script.read_text()
        assert 'tools/microsoft_group_admin_release_profile.py' in text
        assert 'JASON_M365_GROUP_ADMIN_PROFILE=$M365_GROUP_PROFILE' in text
        assert '--omit-microsoft-group-binds-on-rollback' in text
        assert '/opt/jason/bootstrap/secrets/openbao/microsoft-graph-group-' in text
        assert '/var/lib/jason/runtime-secrets/openbao/microsoft-graph-group-' not in text
        assert 'stat -c' in text and '0:1000:640' in text
        assert '"$M365_GROUP_PROFILE"' in text
        assert text.count("--add-readonly-bind") >= 1
        for role in ("read", "write"):
            assert f'microsoft-group-' in text
            assert f"microsoft-graph-group-" in text
    assert "JASON_M365_GROUP_ADMIN_PROFILE" in (
        ROOT / "infrastructure/jason-runtime/compose.yaml").read_text()


@pytest.mark.parametrize("live,image", (
    ("jason-runtime", "jason-runtime:rollback-current"),
    ("jason-mcp-pilot", "jason-mcp:rollback-current"),
))
def test_container_rollback_drops_only_four_group_app_role_mounts(monkeypatch, tmp_path, live, image):
    existing = tmp_path / "untouched"
    existing.write_text("unrelated read-only mount")
    mounts = [{"Source": str(existing), "Destination": "/run/untouched",
               "Type": "bind", "RW": False}]
    for idx, destination in enumerate(DESTINATIONS):
        part = tmp_path / f"role-{idx}"
        part.write_text("credential-present")
        mounts.append({"Source": str(part), "Destination": destination,
                       "Type": "bind", "RW": False})
    monkeypatch.setattr(deploy_live_container, "_inspect", lambda _: {
        "Config": {"Env": ["JASON_SOURCE_REVISION=old"], "User": "1000:1000",
                   "WorkingDir": "/app", "Labels": {}, "Healthcheck": None},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"},
                       "ReadonlyRootfs": True, "Privileged": False,
                       "CapDrop": ["ALL"], "CapAdd": [],
                       "SecurityOpt": ["no-new-privileges:true"],
                       "Tmpfs": {}, "PortBindings": {}, "NetworkMode": "bridge",
                       "LogConfig": {"Type": "json-file", "Config": {}}},
        "Mounts": mounts, "NetworkSettings": {"Networks": {"bridge": {}}},
    })
    cmd, env, _, _ = deploy_live_container._build_create_command(
        live=live, image=image,
        source_revision="f" * 40, harden=True,
        set_env=("JASON_M365_GROUP_ADMIN_PROFILE=",),
        omit_readonly_bind_destinations=DESTINATIONS,
    )
    mounts_cli = " ".join(cmd)
    assert "/run/untouched" in mounts_cli
    assert "type=bind,src="+str(existing) in mounts_cli
    assert all(dest not in mounts_cli for dest in DESTINATIONS)
    assert env["JASON_M365_GROUP_ADMIN_PROFILE"] == ""


def test_writable_mount_never_removed_during_m365_rollback(monkeypatch, tmp_path):
    from test_deploy_live_container_extensions import _live
    original = tmp_path / "original"
    original.write_text("untouched")
    c = _live(original)
    c["Mounts"].append({"Type": "bind", "Source": str(original),
                         "Destination": DESTINATIONS[0], "RW": True})
    monkeypatch.setattr(deploy_live_container, "_inspect", lambda _: c)
    with pytest.raises(ValueError, match="cannot omit writable"):
        deploy_live_container._build_create_command(
            live="jason-runtime", image="jason-runtime:rollback-current",
            source_revision="f"*40, harden=True,
            omit_readonly_bind_destinations=DESTINATIONS,
        )


@pytest.mark.parametrize("live,image,env", (
    ("jason-runtime", "jason-mcp:rollback-current", "JASON_M365_GROUP_ADMIN_PROFILE="),
    ("jason-mcp-pilot", "jason-mcp:production", "JASON_M365_GROUP_ADMIN_PROFILE="),
    ("jason-runtime", "jason-runtime:rollback-current", "JASON_M365_GROUP_ADMIN_PROFILE=enabled"),
    ("jason-runtime", "jason-runtime:rollback-current", None),
))
def test_group_mount_omission_cli_rejects_nonrollback(monkeypatch, live, image, env):
    cmd = ["deploy_live_container.py",
           "--live", live, "--image", image,
           "--rollback", "test-rollback",
           "--source-revision", "f"*40,
           "--health-url", "http://127.0.0.1:8080/healthz",
           "--omit-microsoft-group-binds-on-rollback"]
    if env is not None: cmd += ["--set-env", env]
    monkeypatch.setattr(sys, "argv", cmd)
    with pytest.raises(SystemExit) as exc:
        deploy_live_container.main()
    assert exc.value.code == 2
