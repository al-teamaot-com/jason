"""Offline fixed-argv Docker adapter tests. Never starts Docker or a Gateway."""
from __future__ import annotations

import copy
from hashlib import sha256
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
    "Config": {
        "Labels": {
            "com.aot.jason.component": "pmv4-shadow",
            "com.docker.compose.project": SHADOW_PROJECT,
            "com.docker.compose.service": SERVICE,
        },
        "User": "1000:1000",
        "Env": ["HOME=/home/node", "OPENCLAW_GATEWAY_TOKEN=synthetic-only"],
    },
    "HostConfig": {
        "NetworkMode": "none", "ReadonlyRootfs": True,
        "Privileged": False, "PortBindings": {},
        "CapDrop": ["ALL"], "CapAdd": None,
        "SecurityOpt": ["no-new-privileges:true"],
        "Init": True, "RestartPolicy": {"Name": "no"},
        "PidsLimit": 256, "Memory": 2 * 1024 * 1024 * 1024,
        "NanoCpus": 1_000_000_000, "PublishAllPorts": False,
        "Devices": None,
        "Binds": ["jason-pmv4-shadow-state:/home/node/.openclaw:rw"],
    },
    "Mounts": [
        {"Type": "volume", "Name": "jason-pmv4-shadow-state",
         "Destination": "/home/node/.openclaw"},
        {"Type": "tmpfs", "Destination": "/tmp"},
    ],
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
        bundle = self.release / "bundle" / "config" / "pmv4-shadow"
        bundle.mkdir(parents=True)
        (bundle / "docker-compose.yml").write_text(
            'services:\n  pmv4-shadow-gateway:\n    mem_limit: "2g"\n'
        )
        self.compose_sha = sha256((bundle / "docker-compose.yml").read_bytes()).hexdigest()
        (self.release / "release-manifest.json").write_text(json.dumps({
            "image_digest": DIGEST, "compose_sha256": self.compose_sha,
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
            health_wait_seconds=0,
        )

    def test_activates_only_own_isolated_project(self):
        self.adapter.activate_shadow(self.release)
        self.assertTrue(self.adapter.verify_shadow_and_core(self.release))
        flattened = [" ".join(cmd) for cmd, _ in self.commands]
        self.assertTrue(any("--project-name " + SHADOW_PROJECT in command
                            and "up --detach" in command and "--pull never" in command
                            and str(self.release / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml") in command
                            for command in flattened))
        self.assertTrue(all(SHADOW_NAME in cmd or "pmv4-shadow" in " ".join(cmd)
                            or "image inspect" in " ".join(cmd)
                            for cmd, _ in self.commands))

    def test_immutable_candidate_compose_replaces_outdated_root_template(self):
        self.adapter.activate_shadow(self.release)
        up = [args for args, _ in self.commands if "up" in args]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0][up[0].index("-f")+1],
                         str(self.release / "bundle" / "config" /
                             "pmv4-shadow" / "docker-compose.yml"))
        self.assertNotIn(str(self.root / "control" / "docker-compose.yml"),
                         up[0])
        self.assertEqual(self.inspect_data["HostConfig"]["Memory"],
                         2 * 1024 * 1024 * 1024)
        self.assertEqual(self.inspect_data["HostConfig"]["PidsLimit"], 256)

    def _set_signed_memory(self, value: str) -> None:
        path = self.release / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml"
        prior = path.read_text()
        self.assertEqual(prior.count('mem_limit: "2g"'),1)
        path.write_text(prior.replace('mem_limit: "2g"',
                                      f'mem_limit: "{value}"'))
        doc = self.release / "release-manifest.json"
        manifest = json.loads(doc.read_text())
        manifest["compose_sha256"] = sha256(path.read_bytes()).hexdigest()
        doc.write_text(json.dumps(manifest))

    def test_approved_signed_4gb_accepts_only_4gb_actual_runtime(self):
        self._set_signed_memory("4g")
        old_run = self.adapter.runner
        def fixed_runner(argv,**kw):
            completed=old_run(argv,**kw)
            if "up" in argv:
                self.inspect_data["HostConfig"]["Memory"]=4*1024**3
            return completed
        self.adapter.runner=fixed_runner
        self.adapter.activate_shadow(self.release)
        self.assertEqual(self.inspect_data["HostConfig"]["Memory"],4*1024**3)
        self.assertTrue(self.adapter.verify_shadow_and_core(self.release))
        self.assertEqual(self.adapter._signed_memory_bytes(self.release),4*1024**3)

    def test_signed_4gb_rejects_successful_compose_with_2gb_actual(self):
        self._set_signed_memory("4g")
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
            self.adapter.activate_shadow(self.release)
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
            self.adapter.verify_shadow_and_core(self.release)

    def test_exact_signed_2gb_rollback_after_4gb_container(self):
        original_release=self.release
        newer=self.root / "releases" / ("b"*40)
        newer.mkdir()
        old_path=original_release / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml"
        new_path=newer / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml"
        new_path.parent.mkdir(parents=True)
        new_path.write_text(old_path.read_text().replace(
            'mem_limit: "2g"','mem_limit: "4g"'
        ))
        (newer/"release-manifest.json").write_text(json.dumps({
            "image_digest":DIGEST,"compose_sha256":sha256(new_path.read_bytes()).hexdigest()
        }))
        old_run=self.adapter.runner
        def transition_runner(argv,**kw):
            completed=old_run(argv,**kw)
            if "up" in argv:
                compose=argv[argv.index("-f")+1]
                self.inspect_data["HostConfig"]["Memory"]=(
                    4*1024**3 if str(new_path)==compose else 2*1024**3
                )
            return completed
        self.adapter.runner=transition_runner
        self.adapter.activate_shadow(newer)
        self.assertEqual(self.inspect_data["HostConfig"]["Memory"],4*1024**3)
        self.assertTrue(self.adapter.verify_shadow_and_core(newer))
        self.adapter.restore_shadow(original_release)
        self.assertEqual(self.inspect_data["HostConfig"]["Memory"],2*1024**3)
        self.assertTrue(self.adapter.verify_shadow_and_core(original_release))
        up=[args[args.index("-f")+1] for args,_ in self.commands if "up" in args]
        self.assertEqual(up,[str(new_path),str(old_path)])

    def test_unpinned_memory_five_gigabytes_fails_closed(self):
        self._set_signed_memory("5g")
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_SIGNED_MEMORY_PROFILE_INVALID"):
            self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in args for args,_ in self.commands))

    def test_signed_memory_duplicate_or_unexpected_value_denied(self):
        for profile in ('    mem_limit: "2g"\n    mem_limit: "4g"\n',
                        '    mem_limit: "512m"\n',
                        '    mem_limit: "0"\n'):
            with self.subTest(profile=profile):
                self.commands.clear()
                path=self.release/"bundle"/"config"/"pmv4-shadow"/"docker-compose.yml"
                path.write_text('services:\n  pmv4-shadow-gateway:\n'+profile)
                manifest=self.release/"release-manifest.json"
                doc=json.loads(manifest.read_text())
                doc["compose_sha256"]=sha256(path.read_bytes()).hexdigest()
                manifest.write_text(json.dumps(doc))
                with self.assertRaisesRegex(PermissionError,
                                            "SHADOW_SIGNED_MEMORY_PROFILE_INVALID"):
                    self.adapter.activate_shadow(self.release)
                self.assertFalse(any("up" in args for args,_ in self.commands))

    def test_trusted_inspection_only_allows_reviewed_generation_limits(self):
        for memory in (0,1*1024**3,3*1024**3,5*1024**3,
                       "4294967296", True):
            with self.subTest(memory=memory):
                self.inspect_data=copy.deepcopy(RUNNING)
                self.inspect_data["HostConfig"]["Memory"]=memory
                with self.assertRaisesRegex(PermissionError,
                                            "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
                    self.adapter._owned_or_absent()
        self.inspect_data=copy.deepcopy(RUNNING)
        self.inspect_data["HostConfig"]["Memory"]=4*1024**3
        self.assertIsNotNone(self.adapter._owned_or_absent())
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
            self.adapter._owned_or_absent(expected_memory_bytes=2*1024**3)
        self.assertIsNotNone(self.adapter._owned_or_absent(
            expected_memory_bytes=4*1024**3))

    def test_candidate_compose_source_tamper_denied_before_any_docker_up(self):
        path = self.release / "bundle" / "config" / "pmv4-shadow" / "docker-compose.yml"
        path.write_text("arbitrary-change-after-reviewed-manifest")
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_IMMUTABLE_COMPOSE_HASH_MISMATCH"):
            self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in x[0] for x in self.commands))

    def test_manifest_hash_substitution_is_not_trusted(self):
        manifest = self.release / "release-manifest.json"
        manifest.write_text(json.dumps({
            "image_digest": DIGEST,
            "compose_sha256": "0" * 64,
        }))
        with self.assertRaisesRegex(PermissionError,
                                    "SHADOW_IMMUTABLE_COMPOSE_HASH_MISMATCH"):
            self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in x[0] for x in self.commands))

    def test_old_and_expanded_resource_profiles_both_rejected(self):
        for pids,mem,cpus in ((64,512*1024*1024,500_000_000),
                              (512,4*1024*1024*1024,2_000_000_000)):
            self.inspect_data = copy.deepcopy(RUNNING)
            self.inspect_data["HostConfig"].update(
                PidsLimit=pids,Memory=mem,NanoCpus=cpus)
            with self.subTest(pids=pids):
                with self.assertRaisesRegex(PermissionError,
                                            "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
                    self.adapter.activate_shadow(self.release)
        self.assertFalse(any("up" in x[0] for x in self.commands))

    def test_health_wait_budget_covers_120sec_start_period(self):
        probe = DockerShadowAdapter(
            root=self.root, core_continuity_probe=lambda: True,
            runner=self.adapter.runner, production=False,
        )
        self.assertGreater(probe.health_wait_seconds, 120)
        self.assertLessEqual(probe.health_wait_seconds, 300)

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

    def test_starting_gateway_waits_until_healthy_then_checks_core(self):
        self.adapter.activate_shadow(self.release)
        self.inspect_data["State"]["Health"]["Status"] = "starting"
        time_elapsed = [0.0]
        probes = [0]
        def sleeper(seconds):
            time_elapsed[0] += seconds
            if time_elapsed[0] >= 2:
                self.inspect_data["State"]["Health"]["Status"] = "healthy"
        self.adapter.clock = lambda: time_elapsed[0]
        self.adapter.sleeper = sleeper
        self.adapter.health_wait_seconds = 10
        self.adapter.core_continuity_probe = lambda: probes.__setitem__(0, probes[0]+1) or True
        self.assertTrue(self.adapter.verify_shadow_and_core(self.release))
        self.assertEqual(probes[0], 1)
        self.assertEqual(time_elapsed[0], 2.0)

    def test_wait_is_bounded_and_does_not_reboot_or_restart(self):
        self.adapter.activate_shadow(self.release)
        self.inspect_data["State"]["Health"]["Status"] = "starting"
        time_elapsed = [0.0]
        self.adapter.clock = lambda: time_elapsed[0]
        self.adapter.sleeper = lambda seconds: time_elapsed.__setitem__(0, time_elapsed[0]+seconds)
        self.adapter.health_wait_seconds = 3
        self.assertFalse(self.adapter.verify_shadow_and_core(self.release))
        self.assertEqual(time_elapsed[0], 3.0)
        self.assertFalse(any("restart" in a or "stop" in a for a,_ in self.commands))

    def test_wrong_image_does_not_wait_even_when_gateway_starting(self):
        self.adapter.activate_shadow(self.release)
        self.inspect_data["Image"] = "sha256:"+"e"*64
        self.inspect_data["State"]["Health"]["Status"] = "starting"
        self.adapter.health_wait_seconds = 120
        self.adapter.sleeper = lambda _: self.fail("waited on untrusted image")
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

    def test_real_docker_29_missing_object_format_is_exactly_absent(self):
        def docker29(argv,**kwargs):
            self.assertEqual(argv,
                             ["/usr/bin/docker","inspect",SHADOW_NAME])
            return subprocess.CompletedProcess(
                argv,1,"[]\n","error: no such object: "+SHADOW_NAME+"\n",
            )
        self.adapter.runner=docker29
        self.assertIsNone(self.adapter._owned_or_absent())

    def test_docker29_missing_object_requires_exact_name_and_diagnostic(self):
        for code,out,err in (
            (1,"[]\n","error: no such object: unrelated-container\n"),
            (1,"[]\n","permission denied\n"),
            (1,"[]\n","Cannot connect to the Docker daemon\n"),
            (1,"other","error: no such object: "+SHADOW_NAME+"\n"),
            (1,"[]\n","error: no such object: "+SHADOW_NAME+"\nextra"),
            (2,"[]\n","error: no such object: "+SHADOW_NAME+"\n"),
        ):
            def incorrect(argv,**kwargs):
                return subprocess.CompletedProcess(argv,code,out,err)
            self.adapter.runner=incorrect
            with self.subTest(code=code,err=err):
                with self.assertRaisesRegex(PermissionError,
                                            "SHADOW_INSPECT_UNAVAILABLE"):
                    self.adapter._owned_or_absent()

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

    def test_real_docker29_named_volume_bind_and_mount_are_accepted(self):
        self.inspect_data = copy.deepcopy(RUNNING)
        self.assertEqual(self.inspect_data["HostConfig"]["Binds"], [
            "jason-pmv4-shadow-state:/home/node/.openclaw:rw",
        ])
        self.assertTrue(self.adapter._owned_or_absent())

    def test_only_exact_approved_named_volume_bind_is_permitted(self):
        variants = (
            ["/etc:/etc:ro"],
            ["jason-pmv4-shadow-state:/home/node/.openclaw:ro"],
            ["jason-pmv4-shadow-state:/tmp:rw"],
            ["other-volume:/home/node/.openclaw:rw"],
            ["jason-pmv4-shadow-state:/home/node/.openclaw:rw",
             "/var/lib/jason:/mnt:ro"],
        )
        for value in variants:
            with self.subTest(value=value):
                self.inspect_data = copy.deepcopy(RUNNING)
                self.inspect_data["HostConfig"]["Binds"] = value
                with self.assertRaisesRegex(PermissionError,
                                            "SHADOW_RUNTIME_SECURITY_PROFILE_DRIFT"):
                    self.adapter._owned_or_absent()

    def test_inspect_requires_readback_of_effective_security_restrictions(self):
        from copy import deepcopy

        mutations = {
            "privileged_user": lambda d: d["Config"].__setitem__("User", "root"),
            "caps": lambda d: d["HostConfig"].__setitem__("CapDrop", []),
            "extra_cap": lambda d: d["HostConfig"].__setitem__("CapAdd", ["NET_ADMIN"]),
            "security": lambda d: d["HostConfig"].__setitem__("SecurityOpt", []),
            "init": lambda d: d["HostConfig"].__setitem__("Init", False),
            "restart": lambda d: d["HostConfig"]["RestartPolicy"].__setitem__("Name", "always"),
            "pids": lambda d: d["HostConfig"].__setitem__("PidsLimit", 200),
            "memory": lambda d: d["HostConfig"].__setitem__("Memory", 0),
            "cpus": lambda d: d["HostConfig"].__setitem__("NanoCpus", 0),
            "published_ports": lambda d: d["HostConfig"].__setitem__("PublishAllPorts", True),
            "devices": lambda d: d["HostConfig"].__setitem__("Devices", [{"PathOnHost": "/dev/sda"}]),
            "binds": lambda d: d["HostConfig"].__setitem__("Binds", ["/etc:/etc:ro"]),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.inspect_data = deepcopy(RUNNING)
                mutate(self.inspect_data)
                self.commands.clear()
                with self.assertRaisesRegex(PermissionError, "SECURITY_PROFILE_DRIFT"):
                    self.adapter.activate_shadow(self.release)
                self.assertFalse(any("up" in argv for argv, _ in self.commands))

    def test_shadow_mount_name_and_type_must_match_actual_runtime(self):
        from copy import deepcopy
        for name, edit in {
            "wrong_volume": lambda d: d["Mounts"][0].__setitem__("Name", "jason-production-openclaw"),
            "bind_home": lambda d: d["Mounts"][0].__setitem__("Type", "bind"),
            "missing_home": lambda d: d["Mounts"].pop(0),
            "extra_volume": lambda d: d["Mounts"].append(
                {"Type": "volume", "Destination": "/var/lib/jason"}),
            "bind_tmp": lambda d: d["Mounts"][1].__setitem__("Type", "bind"),
        }.items():
            with self.subTest(name=name):
                self.inspect_data = deepcopy(RUNNING)
                edit(self.inspect_data)
                self.commands.clear()
                with self.assertRaisesRegex(PermissionError, "UNAPPROVED_HOST_MOUNT"):
                    self.adapter.activate_shadow(self.release)
                self.assertFalse(any("up" in argv for argv, _ in self.commands))

    def test_no_separately_billed_api_key_or_provider_secrets_in_shadow(self):
        from copy import deepcopy
        for name in ("OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
                     "ANTHROPIC_API_KEY", "AUTOTASK_API_KEY",
                     "AWS_ACCESS_KEY_ID"):
            with self.subTest(name=name):
                self.inspect_data = deepcopy(RUNNING)
                self.inspect_data["Config"]["Env"].append(name + "=fake-placeholder")
                self.commands.clear()
                with self.assertRaisesRegex(PermissionError, "PROHIBITED_PROVIDER_CREDENTIAL_ENV"):
                    self.adapter.activate_shadow(self.release)
                self.assertFalse(any("up" in argv for argv, _ in self.commands))



if __name__ == "__main__":
    unittest.main()
