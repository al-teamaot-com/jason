"""Offline fixed-argv Docker adapter tests. Never starts Docker or a Gateway."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pmv4_shadow_docker_adapter import (
    DockerShadowAdapter, SHADOW_NAME, SHADOW_PROJECT, SERVICE,
)
from pmv4_shadow_release import ShadowReleaseDenied

DIGEST = "sha256:" + "a"*64
RUNNING = {
    "Image": DIGEST,
    "Config": {"Labels": {
        "com.aot.jason.component": "pmv4-shadow",
        "com.docker.compose.project": SHADOW_PROJECT,
        "com.docker.compose.service": SERVICE,
    }},
    "HostConfig": {
        "NetworkMode": "none", "ReadonlyRootfs": True,
        "Privileged": False, "PortBindings": {},
    },
    "Mounts": [{"Type": "volume", "Destination": "/home/node/.openclaw"}],
    "State": {"Running": True, "Health": {"Status": "healthy"}},
}


class DockerAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pmv4-docker-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "shadow"
        (self.root / "control").mkdir(parents=True)
        (self.root / "control" / "docker-compose.yml").write_text("fake-source-only")
        token = self.root / "control" / "gateway-token"
        token.write_text("offline-fake-token-not-for-production-" + "a"*32)
        token.chmod(0o600)
        self.release = self.root / "releases" / ("a"*40)
        self.release.mkdir(parents=True)
        (self.release / "release-manifest.json").write_text(json.dumps({
            "image_digest": DIGEST,
        }))
        self.commands = []
        self.inspect_data = None
        self.core_ok = True
        self.daemon_down = False

        def fake_runner(argv, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.commands.append((argv, kwargs.get("env")))
            if argv[:2] == ["/usr/bin/docker", "inspect"]:
                if self.daemon_down:
                    return subprocess.CompletedProcess(argv, 1, "",
                                                       "Cannot connect to the Docker daemon")
                if self.inspect_data is None:
                    return subprocess.CompletedProcess(argv, 1, "",
                                                       "Error: No such object: " + SHADOW_NAME)
                return subprocess.CompletedProcess(argv, 0,
                                                   json.dumps([self.inspect_data]), "")
            if argv[:3] == ["/usr/bin/docker", "image", "inspect"]:
                return subprocess.CompletedProcess(argv, 0, json.dumps([{"Id": DIGEST}]), "")
            if "up" in argv:
                self.inspect_data = copy.deepcopy(RUNNING)
            elif "down" in argv:
                self.inspect_data = None
            return subprocess.CompletedProcess(argv, 0, "ok", "")

        self.adapter = DockerShadowAdapter(
            root=self.root, core_continuity_probe=lambda: self.core_ok,
            runner=fake_runner, production=False,
        )

    def test_activates_only_own_isolated_project(self):
        self.adapter.activate_shadow(self.release)
        self.assertTrue(self.adapter.verify_shadow_and_core(self.release))
        flattened = [" ".join(cmd) for cmd, _ in self.commands]
        self.assertTrue(any("--project-name " + SHADOW_PROJECT in command
                            and "up --detach" in command and "--pull never" in command
                            for command in flattened))
        self.assertTrue(all(SHADOW_NAME in cmd or "pmv4-shadow" in " ".join(cmd)
                            or "image inspect" in " ".join(cmd)
                            for cmd, _ in self.commands))

    def test_core_probe_must_confirm(self):
        self.adapter.activate_shadow(self.release)
        self.core_ok = False
        self.assertFalse(self.adapter.verify_shadow_and_core(self.release))

    def test_healthy_wrong_image_is_not_accepted(self):
        self.adapter.activate_shadow(self.release)
        self.inspect_data["Image"] = "sha256:" + "f"*64
        self.assertFalse(self.adapter.verify_shadow_and_core(self.release))

    def test_unhealthy_gateway_does_not_pass(self):
        self.adapter.activate_shadow(self.release)
        self.inspect_data["State"]["Health"]["Status"] = "starting"
        self.assertFalse(self.adapter.verify_shadow_and_core(self.release))

    def test_other_project_collision_refused_before_activation(self):
        self.inspect_data = copy.deepcopy(RUNNING)
        self.inspect_data["Config"]["Labels"]["com.docker.compose.project"] = "openclaw"
        with self.assertRaisesRegex(PermissionError, "OWNERSHIP_OR_ISOLATION"):
            self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in x[0] for x in self.commands))

    def test_wrong_network_or_host_bind_refused(self):
        for mutation in ("network", "bind"):
            self.inspect_data = copy.deepcopy(RUNNING)
            if mutation == "network":
                self.inspect_data["HostConfig"]["NetworkMode"] = "host"
            else:
                self.inspect_data["Mounts"] = [{"Type": "bind",
                                                 "Destination": "/var/lib/jason/openclaw"}]
            with self.assertRaisesRegex(PermissionError, "OWNERSHIP_OR_ISOLATION|UNAPPROVED_HOST_MOUNT"):
                self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in x[0] for x in self.commands))

    def test_docker_daemon_failure_is_not_treated_as_empty_shadow(self):
        self.daemon_down = True
        with self.assertRaisesRegex(PermissionError, "SHADOW_INSPECT_UNAVAILABLE"):
            self.adapter.activate_shadow(self.release)

    def test_initial_empty_baseline_rolls_back_only_shadow_project(self):
        self.inspect_data = copy.deepcopy(RUNNING)
        baseline = self.root / "releases" / ("0"*40)
        baseline.mkdir()
        (baseline / "baseline.json").write_text(json.dumps({
            "schema_version": "1.0", "service": "jason-pmv4-shadow",
            "baseline": "no_prior_shadow_runtime",
        }))
        self.adapter.restore_shadow(baseline)
        self.assertIsNone(self.inspect_data)
        downs = [args for args, _ in self.commands if "down" in args]
        self.assertEqual(len(downs), 1)
        self.assertIn(SHADOW_PROJECT, downs[0])
        self.assertNotIn("--volumes", downs[0])

    def test_token_absent_refuses_activation(self):
        (self.root / "control" / "gateway-token").unlink()
        with self.assertRaisesRegex(PermissionError, "TOKEN_NOT_PROVISIONED"):
            self.adapter.activate_shadow(self.release)

    def test_runtime_manifest_requires_pinned_image(self):
        (self.release / "release-manifest.json").write_text(json.dumps({
            "image_digest": "openclaw:latest",
        }))
        with self.assertRaisesRegex(PermissionError, "SHADOW_IMAGE_NOT_PINNED"):
            self.adapter.activate_shadow(self.release)


if __name__ == "__main__":
    unittest.main()
