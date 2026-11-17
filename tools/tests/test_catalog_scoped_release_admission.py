"""Offline source-proof, rollback and authorization tests. No live API access."""
from __future__ import annotations

from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from tools import catalog_scoped_release_admission as a

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / a.MANIFEST_FILE).read_text())


def observed(manifest=MANIFEST):
    return {
        "runtime_revision":manifest["rollback_sha"],
        "mcp_revision":manifest["rollback_sha"],
        "host_revision":manifest["rollback_sha"],
        "runtime_image_id":manifest["rollback_runtime_image_id"],
        "mcp_image_id":manifest["rollback_mcp_image_id"],
        "candidate_runtime_image_id":manifest["runtime_image_id"],
        "candidate_mcp_image_id":manifest["mcp_image_id"],
        "candidate_runtime_label":manifest["snapshot_sha"],
        "candidate_mcp_label":manifest["snapshot_sha"],
        "runtime_running":True, "mcp_running":True,"runtime_healthy":True,
        "runtime_auth_mode":None, "mcp_grant_admin_profile":None,
        "shared_owner_admin_profile":"",
        "global_owner_allowlist":"person-al", "rollback_images_available":True,
        "freeze_sha256":manifest["freeze_sha256"],
    }


def test_exact_pinned_manifest_profile_source_and_configuration():
    assert a.PROFILE == MANIFEST["profile"]
    assert set(MANIFEST) == a.REQUIRED
    assert MANIFEST["changed_files"] == sorted(a.ALLOWED_FILES)
    assert a.SNAPSHOT_REF.fullmatch(MANIFEST["snapshot_ref"])
    assert MANIFEST["runtime_settings"] == a.RUNTIME_MODE
    assert MANIFEST["mcp_settings"] == a.MCP_MODE
    assert a.SERVER_FUNCTIONS == {
        "_authority_admin_or_catalog_self", "_authority_grant_audit",
        "list_exact_authority_grants", "grant_exact_authority",
        "revoke_exact_authority_grant", "approve_catalog_scoped_runtime_mcp_release",
    }


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema_version="1.1"),
    lambda d: d.update(profile="wildcard-release"),
    lambda d: d.update(snapshot_ref="refs/heads/main"),
    lambda d: d.update(protected_feature_sha="not-a-revision"),
    lambda d: d.update(runtime_image_id="latest"),
    lambda d: d.update(scope_sha256="0"),
    lambda d: d.update(freeze_sha256="0"),
    lambda d: d.update(rollback_sha=d["snapshot_sha"]),
    lambda d: d.update(runtime_settings={"JASON_AUTOTASK_MUTATION_ENABLED":"true"}),
    lambda d: d.update(mcp_settings={"JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES":"anyone"}),
    lambda d: d.update(changed_files=sorted(a.ALLOWED_FILES)+["tools/pmv4_host_release_guard.py"]),
    lambda d: d.update(changed_files=[]),
    lambda d: d.update(changed_files=["docs/engineering/reviews/CATALOG_SERVICE_IDENTITY_20261117.md"]),
    lambda d: d.update(changed_files=list(reversed(sorted(a.ALLOWED_FILES)))),
    lambda d: d.update(extra_privilege=True),
    lambda d: d.pop("rollback_mcp_image_id"),
])
def test_invalid_manifest_fails_before_release_or_provider_contact(monkeypatch, mutation):
    manifest = deepcopy(MANIFEST)
    mutation(manifest)
    monkeypatch.setattr(a, "git", lambda *args: json.dumps(manifest).encode())
    with pytest.raises(a.CatalogScopeDenied):
        a.load_manifest(Path("/tmp/fixture"),main_sha=MANIFEST["protected_feature_sha"])


def test_manifest_from_immutable_commit_not_worktree(monkeypatch):
    args=[]
    def fake_git(repo,*argv):
        args.append(argv)
        return json.dumps(MANIFEST).encode()
    monkeypatch.setattr(a,"git",fake_git)
    assert a.load_manifest(Path("/tmp/fixture"), main_sha=MANIFEST["protected_feature_sha"]) == MANIFEST
    assert args == [("show",MANIFEST["protected_feature_sha"]+":"+a.MANIFEST_FILE)]


def shared_server_text():
    return "\n\n".join(f"def {name}(*args, **kwargs):\n    return True\n"
                     for name in sorted(a.SERVER_FUNCTIONS))


@pytest.fixture
def fake_source(monkeypatch):
    manifest=deepcopy(MANIFEST)
    manifest["scope_sha256"] = sha256(b"exact-binary-patch").hexdigest()
    state={"origin":"https://github.com/al-teamaot-com/jason.git",
           "published":manifest["snapshot_sha"], "main":MANIFEST["protected_feature_sha"],
           "remote_main":MANIFEST["protected_feature_sha"],
           "files":list(sorted(a.ALLOWED_FILES)), "patch":b"exact-binary-patch",
           "override_blobs":{}, "shared":shared_server_text(),"ci":b"test_autotask_catalog_grant_admin.py test_autotask_catalog_service_identity.py",
           "ancestor":True}
    def fake_git(repo,*cmd):
        if cmd == ("remote","get-url","origin"):
            return state["origin"].encode()
        if cmd == ("ls-remote","origin","refs/heads/main"):
            return (state["remote_main"]+"\trefs/heads/main\n").encode()
        if cmd == ("rev-parse","refs/remotes/origin/main"):
            return (state["main"]+"\n").encode()
        if cmd[:2] == ("diff","--no-renames"):
            return ("\n".join(state["files"])+"\n").encode()
        if cmd[:2] == ("diff","--binary"):
            return state["patch"]
        if cmd[0] == "show":
            key=cmd[1]
            if key.endswith(":"+a.SERVER_PATH):
                return state["override_blobs"].get(key,state["shared"].encode())
            if key.endswith(":.github/workflows/security-regressions.yml"):
                return state["ci"]
            return state["override_blobs"].get(key,b"identical-reviewed-source")
        raise AssertionError(cmd)
    monkeypatch.setattr(a, "git", fake_git)
    original_run=a.subprocess.run
    def fake_run(*args,**kwargs):
        if args[0][0:6]==["git","-c","safe.directory=/tmp/fixture","-C",str(Path("/tmp/fixture")),"merge-base"]:
            return SimpleNamespace(returncode=0 if state["ancestor"] else 1)
        return original_run(*args,**kwargs)
    monkeypatch.setattr(a.subprocess,"run",fake_run)
    return manifest,state


def validate_fake(manifest,state):
    return a.verified_source_scope(Path("/tmp/fixture"),manifest,
        main_sha=state["main"],advertised_snapshot_sha=state["published"])


def test_protected_catalog_scope_source_checks(fake_source):
    manifest,state=fake_source
    result=validate_fake(manifest,state)
    assert result["changed_files"]==sorted(a.ALLOWED_FILES)
    assert result["blob_equality_count"]==len(a.EXACT_BLOBS)
    assert result["shared_function_count"]==6
    assert result["source_diff_sha256"]==manifest["scope_sha256"]


@pytest.mark.parametrize("key,change,expected", [
    ("origin","https://evil.example/jason.git","REPOSITORY_ORIGIN_INVALID"),
    ("origin","https://evil.example/mygithub.com/al-teamaot-com/jason.git","REPOSITORY_ORIGIN_INVALID"),
    ("main","a"*40,"PROTECTED_MAIN_CHANGED"),
    ("published","f"*40,"PUBLISHED_SNAPSHOT_CHANGED"),
    ("files",list(sorted(a.ALLOWED_FILES))+["implementation/runtime_service/src/jason_runtime/main.py"],"SOURCE_PATH_SCOPE_EXPANDED"),
    ("files",[x for x in sorted(a.ALLOWED_FILES) if x!=a.SERVER_PATH],"SOURCE_PATH_SCOPE_EXPANDED"),
    ("patch",b"tampered-delta","SNAPSHOT_SCOPE_DIGEST_CHANGED"),
    ("ci",b"no-security-tests","CATALOG_SECURITY_CI_MISSING"),
    ("ancestor",False,"FEATURE_NOT_PROTECTED"),
])
def test_source_tamper_fails_closed(fake_source,key,change,expected):
    manifest,state=fake_source
    state[key]=change
    with pytest.raises(a.CatalogScopeDenied,match=expected):
        validate_fake(manifest,state)


def test_snapshot_owned_module_tamper_fails_closed(fake_source):
    manifest,state=fake_source
    path=next(iter(a.EXACT_BLOBS))
    state["override_blobs"][manifest["snapshot_sha"]+":"+path]=b"unexpected-implementation-change"
    with pytest.raises(a.CatalogScopeDenied,match="CATALOG_SOURCE_BLOB_CHANGED"):
        validate_fake(manifest,state)


def test_shared_mcp_non_catalog_changes_are_allowed_but_catalog_changes_denied(fake_source):
    manifest,state=fake_source
    path=state["main"]+":"+a.SERVER_PATH
    state["override_blobs"][path]=("def unrelated_ticket_read():\n    return True\n\n"+state["shared"]).encode()
    assert validate_fake(manifest,state)["shared_function_count"]==6
    state["override_blobs"][path]=(state["shared"].replace("return True", "return False", 1)).encode()
    with pytest.raises(a.CatalogScopeDenied,match="CATALOG_SHARED_FUNCTION_CHANGED"):
        validate_fake(manifest,state)


def test_shared_source_syntax_error_or_duplicate_functions_fail_closed():
    with pytest.raises(a.CatalogScopeDenied,match="SHARED_SOURCE_INVALID"):
        a.exact_function_source("def broken(:\n", "broken")
    with pytest.raises(a.CatalogScopeDenied,match="SHARED_FUNCTION_MISSING_OR_DUPLICATE"):
        a.exact_function_source("def same():\n pass\ndef same():\n pass\n", "same")


@pytest.mark.parametrize("key,value", [
    ("runtime_revision","0"*40),("mcp_revision","0"*40),
    ("host_revision","0"*40),("runtime_image_id","sha256:"+"0"*64),
    ("mcp_image_id","sha256:"+"0"*64),
    ("candidate_runtime_image_id","sha256:"+"0"*64),
    ("candidate_mcp_image_id","sha256:"+"0"*64),
    ("candidate_runtime_label","0"*40),("candidate_mcp_label","0"*40),
    ("freeze_sha256","0"*64),("runtime_running",False),
    ("mcp_running",False),("runtime_healthy",False),
    ("runtime_auth_mode","jason_managed"),
    ("mcp_grant_admin_profile","aot-catalog-self-owner-v1"),
    ("global_owner_allowlist","person-al,person-any"),
    ("shared_owner_admin_profile","admin-separated-v1"),
    ("rollback_images_available",False),
])
def test_any_live_rollback_freeze_or_owner_drift_fails_closed(key,value):
    state=observed()
    state[key]=value
    with pytest.raises(a.CatalogScopeDenied):
        a.verify_live_image_evidence(MANIFEST,state)


def test_live_production_and_rollback_pass_only_without_changes():
    result=a.verify_live_image_evidence(MANIFEST,observed())
    assert result["rollback_sha"]==MANIFEST["rollback_sha"]
    assert result["global_owner_permissions_unchanged"] is True


@pytest.mark.parametrize("ci", [
    {"passed":False,"failures":[]},
    {"passed":True,"failures":["SEC-007"]},
    {"passed":True,"failures":None},
    {"passed":True,"failures":[],"required":["runtime-service"]}, {}, None,
])
def test_source_scope_never_accepts_failed_or_missing_protected_ci(ci):
    with pytest.raises(a.CatalogScopeDenied,match="PROTECTED_SECURITY_CI_NOT_GREEN"):
        a.source_scope_receipt(MANIFEST,{},{},ci)


def test_receipt_binds_exact_source_dual_images_and_approval_denied():
    source={"snapshot_source_sha":MANIFEST["snapshot_sha"],"changed_files":sorted(a.ALLOWED_FILES)}
    live=a.verify_live_image_evidence(MANIFEST,observed())
    first=a.source_scope_receipt(MANIFEST,source,live,{"passed":True,"failures":[],"required":["governed-security-regressions"]})
    second=a.source_scope_receipt(MANIFEST,source,live,{"passed":True,"failures":[],"required":["governed-security-regressions"]})
    assert first==second
    assert first["receipt_sha256"]==sha256(json.dumps({k:v for k,v in first.items() if k!="receipt_sha256"},sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    for key in ("production_mutations","provider_writes","owner_approval_recorded","native_production_eligible_record_created"):
        assert first[key] is False
    assert first["status"]=="SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE"
    assert first["separate_exact_release_approval_required"] is True


def test_native_preflight_requires_exact_image_existing_source_and_one_setting(tmp_path,monkeypatch):
    script=tmp_path/"existing-preflight.py"
    script.write_text("# not executed in unit test")
    calls=[]
    def fake_run(argv, **kwargs):
        calls.append(argv)
        live=argv[argv.index("--live")+1]
        kind="runtime" if live=="jason-runtime" else "mcp"
        dest=MANIFEST["runtime_image_id" if kind=="runtime" else "mcp_image_id"]
        src=MANIFEST["rollback_runtime_image_id" if kind=="runtime" else "rollback_mcp_image_id"]
        assert argv[-1]=="--preflight"
        return SimpleNamespace(returncode=0,stdout=(f"PREFLIGHT=PASS\nLIVE_CONTAINER={live}\n"
            f"CANDIDATE_IMAGE_ID={dest}\nSOURCE_IMAGE_ID={src}\nSET_ENV_COUNT=1\n"
            "ADDITIONAL_READONLY_BIND_COUNT=0\n").encode())
    monkeypatch.setattr(a.subprocess,"run",fake_run)
    result=a.verify_native_preflights(MANIFEST,script=script)
    assert result["runtime"]["preflight"]=="PASS"
    assert result["mcp"]["preflight"]=="PASS"
    assert len(calls)==2
    assert all("--harden" in call and "--preflight" in call for call in calls)
    assert all("--owner-approved" not in call and "--deploy" not in call for call in calls)


def test_native_preflight_malformed_or_second_env_denied(tmp_path,monkeypatch):
    script=tmp_path/"preflight.py"
    script.write_text("# inert fixture")
    monkeypatch.setattr(a.subprocess,"run",lambda *arg,**kw:SimpleNamespace(returncode=0,stdout=b"PREFLIGHT=PASS\nSET_ENV_COUNT=2\n"))
    with pytest.raises(a.CatalogScopeDenied,match="NATIVE_PREFLIGHT_READBACK_MISMATCH"):
        a.verify_native_preflights(MANIFEST,script=script)


def test_normal_production_manager_commands_not_approved_by_admission():
    assert a.MCP_MODE=={"JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE":"aot-catalog-self-owner-v1"}
    assert a.RUNTIME_MODE=={"JASON_AUTOTASK_CATALOG_AUTH_MODE":"jason_managed"}
    assert "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES" not in a.MCP_MODE
    assert "JASON_AUTOTASK_MUTATION_ENABLED" not in a.RUNTIME_MODE


def test_host_readback_captures_only_bounded_identity_and_never_secrets(monkeypatch,tmp_path):
    baseline=tmp_path/MANIFEST["rollback_sha"]
    baseline.mkdir()
    installed=tmp_path/"current"
    installed.symlink_to(baseline)
    frozen=tmp_path/"production-deployment-freeze"
    frozen.write_bytes(b'{"status":"active"}')
    containers={
        "jason-runtime":{
            "Image":MANIFEST["rollback_runtime_image_id"],
            "Config":{"Labels":{"com.teamaot.jason.source_revision":MANIFEST["rollback_sha"]},
                      "Env":["PROVIDER_PASSWORD=never-echo-this","OTHER_SECRET=secret"]},
            "State":{"Running":True,"Health":{"Status":"healthy"}},
        },
        "jason-mcp-pilot":{
            "Image":MANIFEST["rollback_mcp_image_id"],
            "Config":{"Labels":{"com.teamaot.jason.source_revision":MANIFEST["rollback_sha"]},
                      "Env":["JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-al",
                             "PRIVATE_KEY_B64=do-not-print"]},
            "State":{"Running":True},
        },
    }
    for key in ("runtime_image_id","mcp_image_id","rollback_runtime_image_id","rollback_mcp_image_id"):
        containers[MANIFEST[key]]={"Id":MANIFEST[key],"Config":{"Labels":{
            "com.teamaot.jason.source_revision":MANIFEST["snapshot_sha"]}}}
    def fake_inspect(*argv):
        assert argv[0]=="docker"
        return containers[argv[-1]]
    monkeypatch.setattr(a,"_inspect_json",fake_inspect)
    result=a.host_readback(MANIFEST,freeze_path=frozen,host_source=installed)
    assert result["runtime_running"] and result["mcp_running"]
    assert result["global_owner_allowlist"]=="person-al"
    assert result["runtime_auth_mode"] is None
    assert result["mcp_grant_admin_profile"] is None
    assert "never-echo-this" not in json.dumps(result)
    assert "do-not-print" not in json.dumps(result)
    scoped=deepcopy(MANIFEST)
    scoped["freeze_sha256"]=sha256(frozen.read_bytes()).hexdigest()
    assert a.verify_live_image_evidence(scoped,result)["live_runtime_health"]=="healthy"
    containers["jason-mcp-pilot"]["Config"]["Env"].append(
        "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-everyone")
    with pytest.raises(a.CatalogScopeDenied,match="DUPLICATE_LIVE_ENVIRONMENT_KEY"):
        a.host_readback(scoped,freeze_path=frozen,host_source=installed)


def test_production_manager_catalog_admit_is_source_only_and_does_not_create_root(tmp_path,monkeypatch,capsys):
    # Import the same native command parser as the deployed release manager,
    # but intercept its preflight dependency in an isolated test process.
    import importlib
    monkeypatch.syspath_prepend(str(ROOT/"tools"))
    runner=importlib.import_module("release_manager_host_runner")
    scoped=importlib.import_module("catalog_scoped_release_admission")
    state=tmp_path/"nonexistent-production-state"
    assert not state.exists()
    monkeypatch.setattr(scoped,"attest_source_scope",lambda repo,*,native_ci_checks:{
        "status":"SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE",
        "owner_approval_recorded":False, "production_mutations":False,
    })
    monkeypatch.setattr(sys,"argv",[
        "release_manager_host_runner.py","--repo",str(tmp_path),"--state-root",
        str(state),"catalog-scope-admit",
    ])
    assert runner.main()==0
    assert json.loads(capsys.readouterr().out)["owner_approval_recorded"] is False
    assert not state.exists()


def test_native_preflight_does_not_claim_owner_authorization_or_release(monkeypatch):
    ci={"passed":True,"failures":[],"required":["governed-security-regressions"]}
    result=a.source_scope_receipt(MANIFEST,{"source":"reviewed"},
        a.verify_live_image_evidence(MANIFEST,observed()),ci)
    assert result["separate_exact_release_approval_required"]
    assert result["separate_catalog_test_write_approval_required"]
    assert result["existing_native_release_promotion_unchanged"]
    assert result["owner_approval_recorded"] is False


def test_source_rejects_invalid_malformed_json_before_scoping(monkeypatch):
    monkeypatch.setattr(a,"git",lambda *args:b"{not valid json")
    with pytest.raises(a.CatalogScopeDenied,match="MANIFEST_UNPARSEABLE"):
        a.load_manifest(Path('/tmp/fixture'),main_sha=MANIFEST["protected_feature_sha"])


def test_snapshot_baseline_drift_must_fail_even_when_feature_merged(fake_source,monkeypatch):
    manifest,state=fake_source
    original_run=a.subprocess.run
    def baseline_missing(*args,**kw):
        if (isinstance(args[0],list) and len(args[0])>4
                and args[0][5:7]==["merge-base","--is-ancestor"]
                and args[0][-2:]==[manifest["rollback_sha"],manifest["snapshot_sha"]]):
            return SimpleNamespace(returncode=1)
        return original_run(*args,**kw)
    monkeypatch.setattr(a.subprocess,"run",baseline_missing)
    with pytest.raises(a.CatalogScopeDenied,match="SNAPSHOT_BASELINE_MISMATCH"):
        validate_fake(manifest,state)


def test_new_non_catalog_mcp_behavior_in_snapshot_denied(fake_source):
    manifest,state=fake_source
    modified=state["shared"]+"\n\ndef unrelated_ticket_write():\n    return False\n"
    state["override_blobs"][manifest["snapshot_sha"]+":"+a.SERVER_PATH]=modified.encode()
    # Keep reviewed catalog functions identical; only the new noncatalog
    # addition must cause the rejection.
    with pytest.raises(a.CatalogScopeDenied,match="NONCATALOG_SHARED_SOURCE_DELTA"):
        validate_fake(manifest,state)


def test_future_catalog_manifests_are_configuration_changes_not_new_code(monkeypatch):
    changed=deepcopy(MANIFEST)
    changed["snapshot_ref"]="refs/heads/prep/catalog-identity-grants-isolated-20261118"
    changed["changed_files"]=["implementation/runtime_service/src/jason_runtime/autotask_procurement.py"]
    monkeypatch.setattr(a,"git",lambda *args:json.dumps(changed).encode())
    assert a.load_manifest(Path("/tmp/fixture"),main_sha=MANIFEST["protected_feature_sha"])["snapshot_ref"].endswith("20261118")
    changed["snapshot_ref"]="refs/heads/sneaky-change"
    with pytest.raises(a.CatalogScopeDenied,match="SNAPSHOT_REF_INVALID"):
        a.load_manifest(Path("/tmp/fixture"),main_sha=MANIFEST["protected_feature_sha"])
