"""Regression: source-enabled Teams UAT never breaks immutable LKG rollback.

Every simulated Docker/systemctl/timeout command is a local disposable stub:
the tests do NOT touch host services, real containers, Teams or providers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "infrastructure/jason-runtime/production-deploy.sh"
RECONCILE = REPO / "tools/reconcile_production_host_services.sh"
LKG = "0dceb0af7498e14fedb35aca71b35ed0a95e2526"
NEXT = "351d8716a26b6065585f8ca8ee587ffa634cd7c2"


def _bin(path: Path, name: str, text: str) -> None:
    dest = path / name
    dest.write_text(text, encoding="utf-8")
    dest.chmod(0o755)


def _deployment_harness(tmp_path: Path, *, actual_image_rev: str) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "candidate-source"
    script = root / "infrastructure/jason-runtime/production-deploy.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(DEPLOY.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)

    tools = root / "tools"
    tools.mkdir()
    _bin(tools, "deploy_live_container.py", """#!/usr/bin/env python3
import json,sys
print("FAKE_DEPLOY_ARGS=" + json.dumps(sys.argv[1:]))
""")
    b = tmp_path / "bin"
    b.mkdir()
    _bin(b, "docker", """#!/usr/bin/env bash
if [ "$1" = "image" ] && [ "$2" = "inspect" ] && [ "$3" = "jason-runtime:rollback-current" ]; then
  echo "$FAKE_IMAGE_REVISION"
  exit 0
fi
echo "UNEXPECTED_DOCKER_CALL" >&2
exit 99
""")
    env = os.environ.copy()
    env.update({
        "PATH": str(b) + os.pathsep + env["PATH"],
        "FAKE_IMAGE_REVISION": actual_image_rev,
        # Prevent touching installed QuickBooks/profile state in the fake deploy.
        "JASON_QUICKBOOKS_READ_PROFILE": "",
        "JASON_SOURCE_REVISION_OVERRIDE": LKG,
        "JASON_RUNTIME_PRODUCTION_IMAGE": "jason-runtime:rollback-current",
    })
    return script, env


def _env_updates(argv: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for idx, value in enumerate(argv):
        if value == "--set-env" and idx + 1 < len(argv):
            k, eq, v = argv[idx + 1].partition("=")
            if eq:
                result[k] = v
    return result


def test_manifestless_lkg_rolls_back_test_flags_off_with_verified_image(tmp_path):
    script, env = _deployment_harness(tmp_path, actual_image_rev=LKG)
    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        env=env, capture_output=True, text=True, check=True,
    )
    line = next(s for s in completed.stdout.splitlines() if s.startswith("FAKE_DEPLOY_ARGS="))
    argv = json.loads(line.split("=", 1)[1])
    updates = _env_updates(argv)
    assert updates["JASON_OWNER_UAT_MODE"] == "off"
    assert updates["JASON_OWNER_UAT_WORKER_ENABLED"] == "false"
    assert updates["JASON_OWNER_UAT_SESSION_ID"] == ""
    assert argv[argv.index("--source-revision") + 1] == LKG
    assert "--preflight" in argv


def test_rollback_refuses_other_image_revision_and_never_invokes_deploy(tmp_path):
    script, env = _deployment_harness(tmp_path, actual_image_rev=NEXT)
    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        env=env, capture_output=True, text=True,
    )
    assert completed.returncode == 2
    assert "rollback image/source revision mismatch" in completed.stderr
    assert "FAKE_DEPLOY_ARGS=" not in completed.stdout


def test_regular_deployment_cannot_use_rollback_manifest_exception(tmp_path):
    script, env = _deployment_harness(tmp_path, actual_image_rev=LKG)
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:production"
    completed = subprocess.run(
        ["bash", str(script), "--preflight"],
        env=env, capture_output=True, text=True,
    )
    # The fake source does not have the ordinary strict UAT source-verifier;
    # it must fail rather than silently taking the rollback-only OFF shortcut.
    assert completed.returncode != 0
    assert "FAKE_DEPLOY_ARGS=" not in completed.stdout


def _grafana_harness(tmp_path: Path, *, succeed_after: int = 1, installed: bool = True):
    script = RECONCILE.read_text(encoding="utf-8")
    start = script.index("step_start post_exporter_grafana_assurance")
    end_text = "step_pass post_exporter_grafana_assurance"
    end = script.index(end_text, start) + len(end_text)
    snippet = script[start:end]
    assert script.index("step_pass exporter_verification") < start
    assert end < script.index("step_start production_drift_guard")
    assert "systemctl start jason-grafana-assurance.service" in snippet
    assert "systemctl show jason-grafana-assurance.service -p Result --value" in snippet

    b = tmp_path / "bin"
    b.mkdir()
    counter = tmp_path / "starts"
    _bin(b, "systemctl", """#!/usr/bin/env bash
case "$1" in
  cat)
    [ "$TEST_ASSURANCE_INSTALLED" = "yes" ]
    exit ;;
  start)
    count=0
    if [ -f "$TEST_ASSURANCE_COUNTER" ]; then count="$(cat "$TEST_ASSURANCE_COUNTER")"; fi
    count=$((count + 1))
    echo "$count" > "$TEST_ASSURANCE_COUNTER"
    [ "$count" -ge "$TEST_ASSURANCE_SUCCEED_AFTER" ] ;;
  show)
    count=0
    if [ -f "$TEST_ASSURANCE_COUNTER" ]; then count="$(cat "$TEST_ASSURANCE_COUNTER")"; fi
    if [ "$count" -ge "$TEST_ASSURANCE_SUCCEED_AFTER" ]; then echo success; else echo exit-code; fi ;;
  status)
    echo "mock assurance failed" ;;
  *) exit 97 ;;
esac
""")
    _bin(b, "timeout", """#!/usr/bin/env bash
shift 3
exec "$@"
""")
    _bin(b, "sleep", "#!/usr/bin/env bash\nexit 0\n")
    env = os.environ.copy()
    env.update({
        "PATH": str(b) + os.pathsep + env["PATH"],
        "TEST_ASSURANCE_INSTALLED": "yes" if installed else "no",
        "TEST_ASSURANCE_COUNTER": str(counter),
        "TEST_ASSURANCE_SUCCEED_AFTER": str(succeed_after),
    })
    command = "step_start() { :; }\nstep_pass() { :; }\n" + snippet
    return subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True), counter


def test_real_assurance_success_is_required_before_drift_guard(tmp_path):
    result, counter = _grafana_harness(tmp_path, succeed_after=2)
    assert result.returncode == 0, result.stderr
    assert "GRAFANA_POST_EXPORTER_ASSURANCE=PASS attempt=2" in result.stdout
    assert counter.read_text().strip() == "2"


def test_missing_prometheus_gauges_still_fail_closed_after_bounded_rechecks(tmp_path):
    result, counter = _grafana_harness(tmp_path, succeed_after=99)
    assert result.returncode == 9
    assert "real Grafana assurance remains failed" in result.stderr
    assert counter.read_text().strip() == "3"


def test_optional_assurance_not_installed_is_identified(tmp_path):
    result, counter = _grafana_harness(tmp_path, installed=False)
    assert result.returncode == 0
    assert "GRAFANA_POST_EXPORTER_ASSURANCE=NOT_INSTALLED" in result.stdout
    assert not counter.exists()
