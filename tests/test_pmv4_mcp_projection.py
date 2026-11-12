"""PMv4 Owner projection is an exact bounded MCP mount contract."""
from __future__ import annotations

from pathlib import Path
import pytest

from tools import deploy_live_container as deploy
from tools import pmv4_mcp_projection as projection


def live(tmp_path, *, mounts=None):
    src = tmp_path / "existing"
    src.write_text("readonly data")
    return {
        "Config": {
            "Env": ["JASON_SOURCE_REVISION=old"], "User": "1000:1000",
            "WorkingDir": "/opt/jason-src", "Labels": {},
            "Healthcheck": None,
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "no"}, "ReadonlyRootfs": True,
            "Privileged": False, "CapDrop": ["ALL"], "CapAdd": [],
            "SecurityOpt": ["no-new-privileges:true"], "Tmpfs": {},
            "PortBindings": {}, "NetworkMode": "jason-core",
            "LogConfig": {},
        },
        "Mounts": mounts if mounts is not None else [
            {"Type": "bind", "Source": str(src),
             "Destination": "/run/existing", "RW": False}
        ],
        "NetworkSettings": {"Networks": {"jason-core": {}}},
    }


def test_issuer_projection_only_adds_three_exact_mounts(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy, "_inspect", lambda _: live(tmp_path))
    seen = []
    monkeypatch.setattr(projection, "validate_source",
                        lambda *, expected_audience: seen.append(expected_audience))
    cmd, env, _, _ = deploy._build_create_command(
        live="jason-mcp-pilot", image="jason-mcp:verified-test",
        source_revision="f" * 40, harden=True,
        set_env=("JASON_PMV4_OWNER_ISSUER_ENABLED=true",),
        pmv4_owner_projection=True,
    )
    assert seen == ["9b9996e9-5c34-48b7-948c-f44f89352f89"]
    for src, dst, writable in projection.EXACT_MOUNTS:
        entry = "type=bind,src=" + src + ",dst=" + dst + (
            "" if writable else ",readonly")
        assert cmd.count(entry) == 1
    assert any(str(projection.DECISIONS) in item for item in cmd)
    assert env["JASON_PMV4_OWNER_ISSUER_ENABLED"] == "true"


@pytest.mark.parametrize("mode", [
    "not_hardened", "wrong_service", "not_explicitly_enabled",
    "inherited_enabled", "conflicting_both",
])
def test_projection_rejects_unsafe_activation(monkeypatch, tmp_path, mode):
    specimen = live(tmp_path)
    if mode == "inherited_enabled":
        specimen["Config"]["Env"].append("JASON_PMV4_OWNER_ISSUER_ENABLED=true")
    monkeypatch.setattr(deploy, "_inspect", lambda _: specimen)
    monkeypatch.setattr(projection, "validate_source", lambda **kw: None)
    opts = dict(
        live="jason-mcp-pilot", image="jason-mcp:test",
        source_revision="f" * 40, harden=True,
        set_env=("JASON_PMV4_OWNER_ISSUER_ENABLED=true",),
        pmv4_owner_projection=True,
    )
    if mode == "not_hardened": opts["harden"] = False
    if mode == "wrong_service": opts["live"] = "jason-runtime"
    if mode == "not_explicitly_enabled": opts["set_env"] = ()
    if mode == "inherited_enabled": opts["set_env"] = ()
    if mode == "conflicting_both": opts["omit_pmv4_owner_projection"] = True
    with pytest.raises(ValueError, match="PMV4_OWNER"):
        deploy._build_create_command(**opts)


def test_exact_rollback_omits_writable_receipts_and_readonly_configuration(monkeypatch, tmp_path):
    mounts = [{
        "Type": "bind", "Source": src, "Destination": dst, "RW": writable
    } for src, dst, writable in projection.EXACT_MOUNTS]
    monkeypatch.setattr(deploy, "_inspect",
                        lambda _: live(tmp_path, mounts=mounts))
    cmd, env, _, _ = deploy._build_create_command(
        live="jason-mcp-pilot", image="jason-mcp:rollback-current",
        source_revision="e" * 40, harden=True,
        set_env=("JASON_PMV4_OWNER_ISSUER_ENABLED=false",),
        omit_pmv4_owner_projection=True,
    )
    assert env["JASON_PMV4_OWNER_ISSUER_ENABLED"] == "false"
    assert not any(src in value for src, _, _ in projection.EXACT_MOUNTS
                   for value in cmd)


@pytest.mark.parametrize("change", ["source", "writable", "mount_type"])
def test_rollback_refuses_untrusted_existing_mount(monkeypatch, tmp_path, change):
    src, dst, writable = projection.EXACT_MOUNTS[1]
    mount = {"Type": "bind", "Source": src, "Destination": dst, "RW": writable}
    if change == "source": mount["Source"] = "/untrusted"
    if change == "writable": mount["RW"] = False
    if change == "mount_type": mount["Type"] = "volume"
    monkeypatch.setattr(deploy, "_inspect",
                        lambda _: live(tmp_path, mounts=[mount]))
    with pytest.raises((ValueError, RuntimeError)):
        deploy._build_create_command(
            live="jason-mcp-pilot", image="jason-mcp:rollback-current",
            source_revision="e" * 40, harden=True,
            set_env=("JASON_PMV4_OWNER_ISSUER_ENABLED=false",),
            omit_pmv4_owner_projection=True,
        )


def test_missing_or_wrong_mode_root_state_denied(monkeypatch, tmp_path):
    monkeypatch.setattr(projection, "SHADOW_ROOT", tmp_path / "absent")
    with pytest.raises(ValueError, match="NOT_PROVISIONED"):
        projection.validate_source(expected_audience="aot-app")
    with pytest.raises(ValueError, match="AUDIENCE_UNPINNED"):
        projection.validate_source(expected_audience="")


def test_source_only_deploy_policy_off_by_default():
    import json
    repo = Path(__file__).resolve().parents[1]
    doc = json.loads((repo / "config/pmv4-owner-issuer-activation.json").read_text())
    assert doc == {
        "schema_version": "1.0",
        "service": "jason-pmv4-shadow",
        "mode": "off",
    }
    text = (repo / "infrastructure/jason-mcp/production-deploy.sh").read_text()
    assert '--pmv4-owner-projection' in text
    assert '--omit-pmv4-owner-projection-on-rollback' in text
    assert 'JASON_PMV4_OWNER_ISSUER_ENABLED=false' in text


def test_mcp_image_context_includes_only_reviewed_pmv4_issuer_modules():
    repo = Path(__file__).resolve().parents[1]
    patterns = (repo / ".dockerignore").read_text().splitlines()
    assert "!tools/" in patterns
    assert "tools/*" in patterns
    allowed_tools = {line for line in patterns if line.startswith("!tools/") and line != "!tools/"}
    assert allowed_tools == {
        "!tools/pmv4_shadow_owner_issuer.py",
        "!tools/pmv4_shadow_release.py",
    }
    image = (repo / "infrastructure/jason-mcp/Dockerfile").read_text()
    assert "COPY tools/pmv4_shadow_owner_issuer.py tools/pmv4_shadow_release.py" in image
    assert "/opt/jason-src/implementation/connectors/openclaw" in image
    assert "python -m pip check" in image
