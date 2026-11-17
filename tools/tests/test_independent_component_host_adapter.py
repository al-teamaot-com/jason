import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.independent_component_host_adapter import IndependentComponentHost
from tools.independent_component_release import ComponentReleaseDenied


def policy(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir()
    p = root / "profiles.json"
    doc = {
        "schema_version": "1.0",
        "components": {
            "financial-statements": {
                "project": "jason-financial-statements",
                "service": "financial-statements",
                "network": "jason-core",
                "role_id_path": "/var/lib/jason/runtime-secrets/openbao/microsoft-sharepoint-write-approle/role-id",
                "secret_id_path": "/var/lib/jason/runtime-secrets/openbao/microsoft-sharepoint-write-approle/secret-id",
                "state_dir": "/var/lib/jason/financial-statements",
                "environment_variables": {
                    "image": "JASON_FINANCIAL_IMAGE",
                    "config": "JASON_FINANCIAL_CONFIG",
                    "boundary": "JASON_FINANCIAL_BOUNDARY",
                    "role_id": "JASON_FINANCIAL_ROLE_ID",
                    "secret_id": "JASON_FINANCIAL_SECRET_ID",
                    "state": "JASON_FINANCIAL_STATE",
                    "network": "JASON_FINANCIAL_NETWORK",
                },
                "volume_targets": {
                    "config": "/etc/jason/financial-statements/config.json",
                    "boundary": "/etc/jason/financial-statements/boundary.sqlite3",
                    "role_id": "/run/jason-financial-secrets/role_id",
                    "secret_id": "/run/jason-financial-secrets/secret_id",
                    "state": "/var/lib/jason/financial-statements",
                },
            },
        },
    }
    p.write_text(json.dumps(doc))
    (root / "production-deployment-freeze").write_text('{"status":"active"}')
    return p


class Guard:
    from contextlib import contextmanager

    @contextmanager
    def host_release_transaction(self):
        yield

    def host_mutation_quiescent(self):
        return True


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.extra_service = False
        self.extra_volume = False
        self.wrong_image = False
        self.wrong_network = False
        self.status = 0

    def __call__(self, args, *, cwd, env, capture_output, text, check, timeout):
        self.commands.append((args, env))
        if "config" in args:
            volumes = [
                {"type": "bind", "source": env["JASON_FINANCIAL_CONFIG"],
                 "target": "/etc/jason/financial-statements/config.json", "read_only": True},
                {"type": "bind", "source": env["JASON_FINANCIAL_BOUNDARY"],
                 "target": "/etc/jason/financial-statements/boundary.sqlite3", "read_only": True},
                {"type": "bind", "source": env["JASON_FINANCIAL_ROLE_ID"],
                 "target": "/run/jason-financial-secrets/role_id", "read_only": True},
                {"type": "bind", "source": env["JASON_FINANCIAL_SECRET_ID"],
                 "target": "/run/jason-financial-secrets/secret_id", "read_only": True},
                {"type": "bind", "source": env["JASON_FINANCIAL_STATE"],
                 "target": "/var/lib/jason/financial-statements", "read_only": False},
            ]
            if self.extra_volume:
                volumes.append({
                    "type": "bind", "source": "/var/lib/jason/authority",
                    "target": "/root/authority", "read_only": False,
                })
            service = {
                "image": ("sha256:" + "0" * 64) if self.wrong_image
                         else env["JASON_FINANCIAL_IMAGE"],
                "read_only": True,
                "user": "1000:1000",
                "volumes": volumes,
            }
            services = {"financial-statements": service}
            if self.extra_service:
                services["jason-runtime"] = dict(service)
            doc = {
                "services": services,
                "networks": {"provider": {
                    "external": True,
                    "name": "jason-core" if not self.wrong_network else "host",
                }},
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(doc))
        return SimpleNamespace(returncode=self.status, stdout="")


def host(tmp_path, runner):
    return IndependentComponentHost(
        production=False, runner=runner, host_guard=Guard(),
        profile_path=policy(tmp_path),
        ci_path=tmp_path / "ci.json",
    )


def manifest():
    return {
        "component_id": "financial-statements",
        "compose_project": "jason-financial-statements",
        "compose_service": "financial-statements",
        "image_digest": "sha256:" + "f" * 64,
        "candidate_sha": "a" * 40,
    }


def test_component_only_compose_install_command_exactly_scoped(tmp_path):
    fake = FakeRunner()
    h = host(tmp_path, fake)
    bundle = tmp_path / "release"
    bundle.mkdir()
    h.activate(bundle, manifest())
    assert len(fake.commands) == 2
    args, env = fake.commands[1]
    assert args == [
        "/usr/bin/docker", "compose", "--project-name", "jason-financial-statements",
        "--file", str(bundle / "compose.yaml"),
        "up", "--detach", "--no-deps", "--no-build", "--force-recreate",
        "financial-statements",
    ]
    assert "JASON_FINANCIAL_ROLE_ID" in env
    assert all(v not in env for v in ("OPENBAO_PASSWORD", "JASON_RUNTIME_PASSWORD"))


@pytest.mark.parametrize("failure", [
    "extra_service", "extra_volume", "wrong_image", "wrong_network",
])
def test_compose_resolution_rejects_cross_component_or_unapproved_mounts(
    tmp_path, failure,
):
    fake = FakeRunner()
    setattr(fake, failure, True)
    h = host(tmp_path, fake)
    bundle = tmp_path / "release"
    bundle.mkdir()
    with pytest.raises(ComponentReleaseDenied, match="COMPOSE_RESOLUTION_DENIED"):
        h.activate(bundle, manifest())
    assert len(fake.commands) == 1


def test_unapproved_component_profile_denied(tmp_path):
    fake = FakeRunner()
    h = host(tmp_path, fake)
    m = manifest()
    m["component_id"] = "new-unknown-service"
    with pytest.raises(ComponentReleaseDenied, match="PROFILE_NOT_APPROVED"):
        h.activate(tmp_path, m)
    assert fake.commands == []


def test_host_adapter_source_cannot_run_with_production_authority(tmp_path):
    fake = FakeRunner()
    with pytest.raises(ComponentReleaseDenied, match="ROOT_INSTALL_REQUIRED"):
        IndependentComponentHost(
            production=True, runner=fake, host_guard=Guard(),
            profile_path=policy(tmp_path),
        )


def test_freeze_callback_does_not_modify_marker(tmp_path):
    fake = FakeRunner()
    h = host(tmp_path, fake)
    marker = h.profile_path.parent / "production-deployment-freeze"
    from hashlib import sha256
    original = marker.read_bytes()
    with h.freeze_transaction(sha256(original).hexdigest()):
        assert marker.read_bytes() == original
    assert marker.read_bytes() == original


def test_freeze_change_detected_on_exit(tmp_path):
    fake = FakeRunner()
    h = host(tmp_path, fake)
    marker = h.profile_path.parent / "production-deployment-freeze"
    from hashlib import sha256
    with pytest.raises(ComponentReleaseDenied, match="FREEZE_CHANGED"):
        with h.freeze_transaction(sha256(marker.read_bytes()).hexdigest()):
            marker.write_text('{"status":"inactive"}')


def test_root_entrypoint_denies_source_worktree_invocation_without_reading_production():
    from tools.independent_component_release_root import main
    with pytest.raises(ComponentReleaseDenied, match="ROOT_ENTRYPOINT_NOT_INSTALLED"):
        main(["promote", "--candidate-sha", "a" * 40])
    with pytest.raises(ComponentReleaseDenied, match="ROOT_ENTRYPOINT_NOT_INSTALLED"):
        main(["recover-interrupted-rollback"])


def test_second_component_can_be_added_by_governed_host_profile_without_code_change(tmp_path):
    from copy import deepcopy
    p = policy(tmp_path)
    data = json.loads(p.read_text())
    second = deepcopy(data["components"]["financial-statements"])
    second["project"] = "jason-second-component"
    second["service"] = "second-component"
    second["state_dir"] = "/var/lib/jason/second-component"
    second["role_id_path"] = "/var/lib/jason/runtime-secrets/openbao/second-component-approle/role-id"
    second["secret_id_path"] = "/var/lib/jason/runtime-secrets/openbao/second-component-approle/secret-id"
    second["environment_variables"] = {
        kind: "JASON_SECOND_" + kind.upper()
        for kind in second["environment_variables"]
    }
    second["volume_targets"] = {
        "config": "/etc/jason/second-component/config.json",
        "boundary": "/etc/jason/second-component/boundary.sqlite3",
        "role_id": "/run/jason-second-secrets/role_id",
        "secret_id": "/run/jason-second-secrets/secret_id",
        "state": "/var/lib/jason/second-component",
    }
    data["components"]["second-component"] = second
    p.write_text(json.dumps(data))
    adapter = IndependentComponentHost(
        production=False, runner=FakeRunner(), host_guard=Guard(),
        profile_path=p, ci_path=tmp_path / "ci.json",
    )
    image = "sha256:" + "a" * 64
    prepared = adapter._env(
        tmp_path,
        {
            "component_id": "second-component",
            "compose_project": "jason-second-component",
            "compose_service": "second-component",
            "image_digest": image,
        },
    )
    assert prepared["JASON_SECOND_IMAGE"] == image
    assert prepared["JASON_SECOND_STATE"] == "/var/lib/jason/second-component"
    assert "JASON_FINANCIAL_ROLE_ID" not in prepared


def test_profile_rejects_shared_credential_directory(tmp_path):
    from copy import deepcopy
    p = policy(tmp_path)
    data = json.loads(p.read_text())
    second = deepcopy(data["components"]["financial-statements"])
    second["project"] = "jason-second-component"
    second["service"] = "second-component"
    second["state_dir"] = "/var/lib/jason/second-component"
    data["components"]["second-component"] = second
    p.write_text(json.dumps(data))
    with pytest.raises(ComponentReleaseDenied, match="PROFILE_ISOLATION_CONFLICT"):
        IndependentComponentHost(
            production=False, runner=FakeRunner(), host_guard=Guard(),
            profile_path=p, ci_path=tmp_path / "ci.json",
        )
