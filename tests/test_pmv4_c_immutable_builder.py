from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools import pmv4_c_immutable_builder as builder
from tools import pmv4_c_atomic_root as root

SOURCE="a"*40

def test_candidate_policy_adds_only_ticket_core(tmp_path):
    config=tmp_path/"config";config.mkdir()
    base={
        "schema_version":"1.0",
        "required_containers":["jason-runtime","jason-mcp-pilot"],
        "allowed_running_containers":[
            "jason-runtime","jason-mcp-pilot","jason-pmv4-shadow-gateway"
        ],
        "allowed_system_units":["a"],
        "required_system_units":["c","b"],
        "required_user_units":["z","a"],
    }
    raw=(json.dumps(base,indent=2)+"\n").encode()
    (config/"production-desired-state.json").write_bytes(raw)
    before,candidate_raw=builder._candidate_policy(tmp_path)
    normalized=json.loads(json.dumps(base))
    for name in ("required_system_units","required_user_units"):
        normalized[name].sort()
    assert before==(json.dumps(normalized,indent=2,sort_keys=True)+"\n").encode()
    assert json.loads(before)==normalized
    candidate=json.loads(candidate_raw)
    assert candidate["required_containers"]==base["required_containers"]
    assert candidate["allowed_system_units"]==base["allowed_system_units"]
    assert candidate["allowed_running_containers"]==(
        base["allowed_running_containers"]+[root.WORKER])

def test_installed_watchdog_byte_shape_matches_root_observed_diff():
    # A read-only privileged diff from 2026-11-17 proved that the active root
    # policy has sorted object keys and alphabetically sorted required unit
    # arrays, with NO addition/deletion of required/allowed entries.
    source_root=Path(builder.__file__).resolve().parents[1]
    raw=(source_root/"config/production-desired-state.json").read_bytes()
    canonical,candidate=builder._candidate_policy(source_root)
    assert hashlib.sha256(raw).hexdigest()==(
        "db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50")
    assert hashlib.sha256(canonical).hexdigest()==(
        "9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804")
    original=json.loads(raw)
    root_format=json.loads(canonical)
    assert set(original)==set(root_format)
    assert all(
        original[key]==root_format[key]
        for key in original
        if key not in ("required_system_units","required_user_units")
    )
    assert all(sorted(original[key])==root_format[key]
               for key in ("required_system_units","required_user_units"))
    next_policy=json.loads(candidate)
    assert next_policy["allowed_running_containers"]==(
        root_format["allowed_running_containers"]+[root.WORKER])
    assert all(next_policy[key]==root_format[key]
               for key in root_format if key!="allowed_running_containers")
    # A deliberately different serialized source ordering cannot silently
    # change any root guard: its exact byte checksum still binds the packet.
    assert canonical!=raw


def test_required_unit_sets_must_be_unique_and_string_only(tmp_path):
    config=tmp_path/"config";config.mkdir()
    template={"schema_version":"1.0","allowed_running_containers":[
        "jason-runtime","jason-pmv4-shadow-gateway"],
        "required_system_units":["a"],"required_user_units":["b"]}
    for key,value in (("required_system_units",["a","a"]),
                      ("required_user_units",["b",3])):
        candidate=json.loads(json.dumps(template));candidate[key]=value
        (config/"production-desired-state.json").write_text(json.dumps(candidate))
        try:builder._candidate_policy(tmp_path)
        except builder.BuilderDenied as exc:
            assert "C_BUILD_WATCHDOG_REQUIRED_UNIT_SET_INVALID" in str(exc)
        else:raise AssertionError("builder accepted untrusted required list")


def test_generated_launcher_orders_root_preflight_before_owner_and_execute(tmp_path):
    plan={
        "candidate_sha":SOURCE,
        "staged_source_files":{
            "tools/a.py":"1"*64,
            "tools/b.py":"2"*64,
        },
    }
    text=builder._launcher(plan,tmp_path/"artifact","3"*64,"4"*64)
    root_pre='sudo /usr/bin/python3 -I -B "$STAGED" --plan "$PLAN" --preflight'
    owner='PYTHONPATH="$ART/src:." /usr/bin/python3 -B "$OWNER" --plan "$PLAN" --authorize'
    execute='sudo /usr/bin/python3 -I -B "$STAGED" --plan "$PLAN" --execute'
    post='sudo /usr/bin/python3 -I -B "$STAGED" --plan "$PLAN" --postflight'
    assert text.index(root_pre) < text.index(owner) < text.index(execute)
    assert text.index(execute) < text.index(post)
    assert "sudo /usr/bin/install -o root -g root -m 0400" in text
    assert "OWNER_APPROVAL_NOT_YET_USED=true; PRODUCTION_MUTATIONS=false" in text
    assert "PMV4_LATER_PHASES_ARE_NOT_AUTHORIZED" in text
    assert "teams" not in text.casefold()
    assert "continue" not in text.casefold()

def test_provider_state_comes_from_exact_projection():
    assert tuple(builder.PROVIDER_STATE)==(
        "/var/lib/jason/openclaw/dnsfilter-mcp",
        "/var/lib/jason/openclaw/quickbooks-production",
    )


def test_builder_uses_atomic_hidden_staging_directory():
    source=Path(builder.__file__).read_text()
    assert '".pmv4-c-"+candidate+".building"' in source
    assert "os.rename(artifact,final_artifact)" in source
    assert "shutil.rmtree(partial)" in source


def test_stage_c_support_set_contains_transaction_dependencies():
    assert {
        "tools/pmv4_c_sqlite_family_handoff.py",
        "tools/pmv4_c_service_manifest.py",
        "tools/pmv4_ticket_core_exact_projection.py",
        "tools/pmv4_host_release_guard.py",
        "tools/pmv4_shadow_ci.py",
        "tools/deploy_live_container.py",
        "tools/pmv4_mcp_projection.py",
    } == set(builder.STAGED_FILES)

def test_stage_c_db_allowlist_is_exact_and_bounded():
    names={Path(x).name for x in builder.DBS}
    assert names=={
        "autonomy-operational-work.sqlite3",
        "playbook-autonomy.sqlite3",
        "autonomy-targeted-wakes.sqlite3",
        "ticket-split.sqlite3",
        "teams-identity-bindings.sqlite3",
        "orchestration-events.sqlite3",
        "governed-execution.sqlite3",
        "reflection.sqlite3",
        "resolution-memory.sqlite3",
        "model-usage.sqlite3",
    }
    assert all(Path(x).parent==Path("/var/lib/jason/openclaw")
               for x in builder.DBS)

def test_ticket_core_dockerfile_has_no_http_exposure():
    dockerfile=(
        Path(builder.__file__).resolve().parents[1]/
        "infrastructure/pmv4-ticket-core/Dockerfile"
    ).read_text()
    assert "\nEXPOSE " not in dockerfile
    assert "ARG JASON_RUNTIME_DEPENDENCY_IMAGE=jason-runtime:production" in dockerfile
    assert "AS runtime-deps" in dockerfile
    assert "COPY --from=runtime-deps /usr/local /usr/local" in dockerfile
    assert "pip install" not in dockerfile
    assert 'CMD ["python", "-m", "jason_runtime.ticket_worker_service"]' in dockerfile
    assert "USER 1000:1000" in dockerfile
