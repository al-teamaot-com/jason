"""No-production execution of the actual container rollout's profile preflight.

Extracts only the shell preflight up to the image/deploy section. Uses fake
docker output and an isolated synthetic source tree; NO container mutation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
V10 = "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10"
V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"
V13 = "itglue-autotask-entra-dynamic-schema-read-catalog-v13"
SCRIPTS = [
    ("infrastructure/jason-runtime/production-deploy.sh", "jason-runtime", "jason-runtime:rollback-current"),
    ("infrastructure/jason-mcp/production-deploy.sh", "jason-mcp-pilot", "jason-mcp:rollback-current"),
]


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "immutable-source"
    (root / "config").mkdir(parents=True)
    (root / "config" / "autotask-entity-read-profile.json").write_text(
        json.dumps({"schema_version": "1.0", "read_profile": V11, "rollback_read_profile": V10})
    )
    bins = tmp_path / "fake-bin"
    bins.mkdir()
    fake = bins / "docker"
    fake.write_text(
        "#!/bin/sh\n"
        "test \"$1\" = inspect || exit 16\n"
        "printf 'JASON_PROVIDER_READ_ACTIVATION_PROFILE=%s\\n' \"$FAKE_LIVE_PROFILE\"\n"
    )
    fake.chmod(0o700)
    return root, bins


def check_preflight(lab, path, live_name, rollback_tag, *,
                    image="candidate", selected=V11, rollback=V10,
                    live=V10, source=V11):
    root, bins = lab
    declaration = root / "config" / "autotask-entity-read-profile.json"
    declaration.write_text(json.dumps({"schema_version": "1.0", "read_profile": source, "rollback_read_profile": V10}))
    source_script = (ROOT / path).read_text()
    marker = '\nif [ -z "$REVISION" ]; then'
    assert marker in source_script
    # An explicit exit happens BEFORE the image/host mutation part of the
    # real script. All preceding preflight instructions are the actual source.
    dry = source_script.split(marker, 1)[0] + '\nprintf "SELECTED_PROFILE=%s\\n" "$AUTOTASK_READ_PROFILE"\n'
    script = root / path
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(dry)
    script.chmod(0o700)
    env = {
        **os.environ,
        "PATH": str(bins) + os.pathsep + os.environ["PATH"],
        "FAKE_LIVE_PROFILE": live,
        "JASON_PROVIDER_READ_ACTIVATION_PROFILE": selected,
        "JASON_PROVIDER_READ_ROLLBACK_PROFILE": rollback,
        "JASON_SOURCE_REVISION_OVERRIDE": "a" * 40,
        "JASON_RUNTIME_PRODUCTION_IMAGE": image,
        "JASON_MCP_PRODUCTION_IMAGE": image,
        "JASON_QUICKBOOKS_READ_PROFILE": "quickbooks-sandbox-read-v1",
    }
    if image == "rollback":
        env["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:rollback-current"
        env["JASON_MCP_PRODUCTION_IMAGE"] = "jason-mcp:rollback-current"
    if not selected:
        env.pop("JASON_PROVIDER_READ_ACTIVATION_PROFILE", None)
    if not rollback:
        env.pop("JASON_PROVIDER_READ_ROLLBACK_PROFILE", None)
    return subprocess.run(
        ["bash", str(script)], cwd=root, env=env, capture_output=True, text=True,
        timeout=12, check=False,
    )


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_forward_v11_is_exactly_source_bound(lab, path, live_name, rollback_tag):
    response = check_preflight(lab, path, live_name, rollback_tag)
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V11 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_rollback_restore_uses_previous_v10_even_if_live_is_v11(
        lab, path, live_name, rollback_tag):
    response = check_preflight(lab, path, live_name, rollback_tag,
                               image="rollback", live=V11)
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V10 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
@pytest.mark.parametrize("selected,rollback,live,source", [
    (V10, V10, V10, V11),
    (V11, V10, V10, "unsupported"),
])
def test_profile_mismatch_or_wrong_live_baseline_refused_before_mutation(
        lab, path, live_name, rollback_tag, selected, rollback, live, source):
    response = check_preflight(
        lab, path, live_name, rollback_tag, selected=selected, rollback=rollback,
        live=live, source=source,
    )
    assert response.returncode != 0
    assert "SELECTED_PROFILE=" not in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_legacy_pm_preflight_without_undeployed_environment_overrides(
        lab, path, live_name, rollback_tag):
    response = check_preflight(lab, path, live_name, rollback_tag,
                               selected="", rollback="", live=V10)
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V11 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_exact_v10_rollback_without_new_controller_env_overrides(
        lab, path, live_name, rollback_tag):
    response = check_preflight(lab, path, live_name, rollback_tag,
                               image="rollback", selected="", rollback="", live=V11)
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V10 in response.stdout

@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_v13_forward_preflight_uses_exact_source_bound_profile_and_v10_lkg(
        lab, path, live_name, rollback_tag):
    response = check_preflight(
        lab, path, live_name, rollback_tag,
        selected=V13, source=V13, rollback=V10, live=V10,
    )
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V13 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_v13_forward_preflight_from_legacy_pm_without_profile_overrides(
        lab, path, live_name, rollback_tag):
    response = check_preflight(
        lab, path, live_name, rollback_tag,
        selected="", source=V13, rollback="", live=V10,
    )
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V13 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_v13_rollback_restores_v10_with_or_without_explicit_override(
        lab, path, live_name, rollback_tag):
    for selected, rollback in ((V13,V10), ("","")):
        response = check_preflight(
            lab, path, live_name, rollback_tag,
            image="rollback", source=V13, selected=selected,
            rollback=rollback, live=V13,
        )
        assert response.returncode == 0, response.stderr
        assert "SELECTED_PROFILE=" + V10 in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
@pytest.mark.parametrize("selected,rollback,live,source", [
    (V11,V10,V10,V13),
    (V13,V11,V10,V13),
    (V13,V10,V11,V13),
    (V13,V10,V10,"unapproved-profile"),
])
def test_v13_mismatched_source_override_rollback_or_live_state_fail_closed(
        lab,path,live_name,rollback_tag,selected,rollback,live,source):
    response = check_preflight(
        lab,path,live_name,rollback_tag,
        selected=selected,rollback=rollback,live=live,source=source,
    )
    assert response.returncode != 0
    assert "SELECTED_PROFILE=" not in response.stdout


@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_v13_to_v13_roll_forward_keeps_v10_rollback_and_source_gate(
        lab,path,live_name,rollback_tag):
    response=check_preflight(lab,path,live_name,rollback_tag,selected=V13,source=V13,rollback=V10,live=V13)
    assert response.returncode == 0, response.stderr
    assert "SELECTED_PROFILE=" + V13 in response.stdout

@pytest.mark.parametrize("path,live_name,rollback_tag", SCRIPTS)
def test_unknown_live_profile_still_denied(lab,path,live_name,rollback_tag):
    response=check_preflight(lab,path,live_name,rollback_tag,selected=V13,source=V13,rollback=V10,live="unknown-profile")
    assert response.returncode != 0
    assert "SELECTED_PROFILE=" not in response.stdout
