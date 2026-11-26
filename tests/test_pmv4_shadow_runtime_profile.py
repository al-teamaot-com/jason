"""Offline static safety assertions for a dedicated PMv4 shadow runtime."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YAML = ROOT / "config/pmv4-shadow/docker-compose.yml"


class ShadowRuntimeProfile(unittest.TestCase):
    def test_no_production_provider_or_host_bindings(self):
        src = YAML.read_text()
        for forbidden in (
            "openclaw-openclaw-gateway-1", "jason-runtime", "jason-mcp",
            "al_admin@", "autotask", "datto", "/var/lib/jason/openclaw",
            "network_mode: host", "privileged: true", "docker.sock", "ports: [80",
        ):
            self.assertNotIn(forbidden, src)
        self.assertIn('network_mode: "none"', src)
        self.assertIn("no-new-privileges:true", src)
        self.assertIn("read_only: true", src)
        self.assertIn('restart: "no"', src)
        self.assertIn('provider-mutation: "disabled"', src)
        self.assertIn('container_name: "jason-pmv4-shadow-gateway"', src)

    def test_compose_valid_with_dry_synthetic_credentials(self):
        # docker compose config does not deploy or call any provider.
        proc = subprocess.run(
            ["docker", "compose", "-f", str(YAML), "--project-name",
             "jason-pmv4-shadow-qa", "config", "--quiet"],
            env={"PATH": "/usr/bin:/bin", "PMV4_SHADOW_IMAGE_SHA": "sha256:" + "a"*64,
                 "PMV4_SHADOW_GATEWAY_TOKEN": "nonproduction-validation-only"},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[:1000])


if __name__ == "__main__":
    unittest.main()
