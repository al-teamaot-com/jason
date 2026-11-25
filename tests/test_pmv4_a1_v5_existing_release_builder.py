"""Synthetic root/owner scope and rollback tests; no production execution."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import ModuleType,SimpleNamespace
import sys

import pytest

from tools import pmv4_a1_v5_existing_release_builder as r


SRC=Path(__file__).resolve().parents[1]
SHA="a"*40
IMAGE="sha256:"+"c"*64


def source(name):
    return (SRC/name).read_text()


def root_code():
    return r.render_root(source(r.SOURCE_FILES[0]),SHA,IMAGE)


def test_v5_recovery_is_bound_to_actual_prior_committed_release():
    text=root_code()
    assert 'CANDIDATE="'+SHA+'"' in text
    assert 'ROLLBACK="'+r.PRIOR+'"' in text
    assert 'ACTION="'+r.ACTION+'"' in text
    assert 'PRIOR_APPROVAL="'+r.PRIOR_APPROVAL+'"' in text
    assert 'PRIOR_IMAGE="'+r.PRIOR_IMAGE+'"' in text
    assert "A1_V5_PRIOR_ROOT_ACCEPTANCE_MISSING" in text
    assert "A1_V5_PRIOR_ROOT_AUDIT_NOT_COMMITTED" in text
    assert "A1_V5_PRIOR_STOPPED_OOM_CONTAINER_CHANGED" in text
    assert "A1_V5_ROOT_HISTORICAL_RECEIPTS_CHANGED" in text
    assert "A1_V4_EXACT_TWO_ROLLED_BACK_RECEIPTS_REQUIRED" not in text
    assert "A1_SHADOW_CONTAINER_ALREADY_PRESENT" not in text
    assert 'and r.get("rollback_sha")==("0"*40)' in text
    assert 'root_secure_random_48' not in text
    assert 'existing_protected_root_token_reused' in text


def test_v5_exact_scope_never_reissues_existing_owner_proof():
    root=root_code()
    own=r.render_owner(source(r.SOURCE_FILES[1]),SHA)
    local=r.render_local(source(r.SOURCE_FILES[2]),SHA,"1"*64,"2"*64)
    assert r.CONFIRM in own
    assert "tools.pmv4_a1_v5_verified_root" in own
    assert '"gateway_secret_generation":"existing_protected_root_token_reused"' in own
    assert '"gateway_secret_generation":"root_secure_random_48"' not in own
    assert r.ACTION in root
    assert "issue_exact_owner_release(" not in root
    assert "verify_exact_owner_release(" in root
    assert "/run/jason-pmv4-a1-v5-"+SHA[:12] in local
    assert "/run/jason-pmv4-a1-v4-" not in local
    assert 'ROOT_SHA="'+("1"*64)+'"' in local
    assert 'OWNER_SHA="'+("2"*64)+'"' in local
    assert "sudo /usr/bin/python3 -I -B" in local
    assert "OWNER_APPROVAL_CREATED=1" in local


def test_root_replaces_only_owned_approved_manifest_and_scope():
    code=root_code()
    start=code.index("def stage_exact(")
    end=code.index("def cleanup_exact_unpromoted(",start)
    own=code[start:end]
    assert "record_file(TARGET/" in own
    assert "intent-replace-root-control" in own
    assert "replaced-root-control" in own
    assert "os.replace(tmp,path)" in own
    assert "record_file(TOKEN," not in own
    assert "secrets.token_urlsafe" not in own
    assert "ROOT/" in own
    assert "A1_V5_PRIOR_ROOT_CONTROL_CHANGED" in own


def test_stop_state_restore_not_start_legacy_oom_gateway():
    code=root_code()
    start=code.index("def restore_prior_shadow_stopped(")
    end=code.index("def controller(",start)
    helper=code[start:end]
    assert '"create","--force-recreate","--no-build","--pull","never"' in helper
    assert '"up","--detach"' not in helper
    assert '"start"' not in helper
    assert "expected_memory_bytes=2*1024**3" in helper
    assert "get(\"Running\") is False" in helper
    assert 'rollback_mode' not in helper
    assert "jason-runtime" not in helper


def test_root_failure_attempts_pointer_and_scope_restore():
    code=root_code()
    start=code.index("def execute()->None:")
    end=code.index("def postflight()->None:")
    body=code[start:end]
    assert 'worker._switch(CURRENT,ROLLBACK)' in body
    assert 'restore_prior_shadow_stopped(adapter,ROOT/"releases"/ROLLBACK)' in body
    assert "restore_prior_root_control()" in body
    assert "cleanup_exact_unpromoted(approval)" in body
    assert 'and adapter._owned_or_absent() is None' not in body
    assert 'A1_V5_PRIOR_POINTER_NOT_RESTORED' in body
    assert 'cleanup_exact_unpromoted(approval)' in body


def test_negative_unreviewed_source_image_and_missing_anchor():
    with pytest.raises(r.V5BuildDenied):
        r.render_root(source(r.SOURCE_FILES[0]),"z"*40,IMAGE)
    with pytest.raises((r.V5BuildDenied,r.v4.CandidateBuildDenied)):
        r.render_root("unsafe",SHA,IMAGE)
    with pytest.raises((r.V5BuildDenied,r.v4.CandidateBuildDenied)):
        r.render_owner("unsafe",SHA)
    with pytest.raises((r.V5BuildDenied,r.v4.CandidateBuildDenied)):
        r.render_local("unsafe",SHA,"1"*64,"2"*64)


@pytest.fixture
def manifest():
    scope={"schema_version":"1.0","service":"jason-pmv4-shadow",
           "candidate_sha":SHA,"rollback_sha":r.PRIOR,
           "provider_writes":False}
    m={"candidate_sha":SHA,"rollback_sha":r.PRIOR,
       "image_digest":IMAGE,"scope_sha256":sha256(r.canonical(scope)).hexdigest(),
       "bundle_sha256":"a"*64}
    e={"status":"preproduction_candidate_not_authorized",
       "source_sha":SHA,"rollback_sha":r.PRIOR,
       "image_digest":IMAGE,"manifest_sha256":sha256(r.canonical(m)).hexdigest(),
       "bundle_sha256":m["bundle_sha256"],
       "source_files":{"config/pmv4-shadow/docker-compose.yml":"f"*64},
       "production_mutations":False,"shadow_activation_performed":False}
    return m,e


def build_plan(manifest):
    m,e=manifest
    return r.build_plan(sha=SHA,image=IMAGE,root_hash="b"*64,evidence=e,
       manifest=m,freeze_sha="c"*64,hold_sha="d"*64,
       shadow_freeze_sha="e"*64,lkg="f"*40,
       runtime_images={"jason-runtime":"sha256:"+"1"*64,
                       "jason-mcp-pilot":"sha256:"+"2"*64})


def test_exact_plan_has_one_owner_no_reused_consent_or_runtime_mutation(manifest):
    p=build_plan(manifest)
    assert p["candidate_sha"]==SHA and p["rollback_sha"]==r.PRIOR
    assert p["action"]==r.ACTION
    assert p["gateway_secret_generation"]=="existing_protected_root_token_reused"
    assert p["owner_consents"]==1
    assert p["standing_authority"] is False
    assert p["root_stage_before_owner_authorization"] is False
    last=p.pop("scope_sha256")
    assert last==sha256(r.canonical(p)).hexdigest()


def test_wrong_prior_rollback_or_stale_manifest_denied(manifest):
    m,e=manifest
    m=dict(m);m["rollback_sha"]="0"*40
    with pytest.raises(r.V5BuildDenied,match="RELEASE_MANIFEST_NOT_CURRENT_PRIOR"):
        r.build_plan(sha=SHA,image=IMAGE,root_hash="b"*64,evidence=e,
            manifest=m,freeze_sha="c"*64,hold_sha="d"*64,
            shadow_freeze_sha="e"*64,lkg="f"*40,
            runtime_images={"jason-runtime":"sha256:"+"1"*64,
                            "jason-mcp-pilot":"sha256:"+"2"*64})
    e=dict(e);e["production_mutations"]=True
    with pytest.raises(r.V5BuildDenied,match="RELEASE_MANIFEST_NOT_CURRENT_PRIOR"):
        r.build_plan(sha=SHA,image=IMAGE,root_hash="b"*64,evidence=e,
            manifest=manifest[0],freeze_sha="c"*64,hold_sha="d"*64,
            shadow_freeze_sha="e"*64,lkg="f"*40,
            runtime_images={"jason-runtime":"sha256:"+"1"*64,
                            "jason-mcp-pilot":"sha256:"+"2"*64})


def test_build_denied_without_verified_protected_main(tmp_path,monkeypatch):
    monkeypatch.setattr(r.packet,"ARTIFACT_PARENT",tmp_path)
    with pytest.raises(r.V5BuildDenied,match="PROTECTED_MAIN_CI_NOT_GREEN"):
        r.prepare(SHA,IMAGE,verify_main=lambda _:False)
    assert list(tmp_path.iterdir())==[]


def test_generated_root_has_no_direct_core_or_mcp_mutation():
    x=root_code()
    start=x.index("def restore_prior_shadow_stopped(")
    end=x.index("def execute()->None:")
    code=x[start:end]
    for bad in ("docker restart jason-runtime","systemctl stop jason-mcp",
                "docker rm jason-runtime","provider_api_key"):
        assert bad not in code
    assert 'host.host_release_transaction()' in x
    assert 'self.root / "control" / "shadow-release.lock"' in source(
        "tools/pmv4_shadow_release.py")


def test_existing_owner_recovery_is_exact_readback_and_no_second_auth():
    code=root_code()
    segment=code.split("def recover_exact_consumed_v5()->None:",1)[1].split(
        "def postflight()->None:",1)[0]
    for required in (
        'verify_exact_owner_release(',
        'expected_candidate_sha',
        'expected_rollback_sha',
        'expected_scope_sha256',
        'expected_manifest_sha256',
        'expected_freeze_sha256',
        'rows[0].get("event")=="begin"',
        'reused_exact_historical_owner_approval":True',
        'A1_V5_RECOVERY_OWNER_SCOPE_DIFFERENT',
        'A1_V5_NATIVE_ACCEPTED_REQUIRES_ROOT_REVIEW',
        'restore_prior_root_control()',
        'cleanup_exact_unpromoted(approval)',
        '_reconcile_pending_rollback_locked(',
    ):
        assert required in segment
    assert "issue_exact_owner_release(" not in segment
    assert "authenticate_owner(" not in segment
    assert "docker stop jason-runtime" not in segment
    assert "reset-failed" not in segment


def test_exact_recovery_launcher_can_only_rollback_consumed_owner():
    result=r.render_recovery_local(SHA,"b"*64)
    assert '[[ "$#" == 1 && "$1" == "--recover" ]]' in result
    assert '[[ -f "$PROOF" && ! -L "$PROOF" ]]' in result
    assert 'ROOT_SHA="'+"b"*64+'"' in result
    assert "sudo /usr/bin/python3 -I -B" in result
    assert "--recover-existing-owner" in result
    assert "--authorize" not in result
    assert "--execute" not in result
    assert "docker restart" not in result
    assert "jason-runtime" not in result
    with pytest.raises(r.V5BuildDenied,match="RECOVERY_LAUNCHER_NOT_PINNED"):
        r.render_recovery_local("not-a-sha","b"*64)


def run_pure_prior_stopped_callback(tmp_path,*,name=None,image=None,memory=None,
                                    running=False):
    import ast
    from tools import pmv4_shadow_release as shadow
    code=root_code()
    tree=ast.parse(code)
    one=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
             and x.name=="restore_prior_shadow_stopped")
    method=ast.Module(body=[one],type_ignores=[])
    seen=[]
    root_name=r.PRIOR if name is None else name
    image=r.PRIOR_IMAGE if image is None else image
    mem=2*1024**3 if memory is None else memory
    class Adapter:
        def _manifest_image(self,prior):return image
        def _candidate_compose(self,prior):return tmp_path/"trusted-prior-compose.yml"
        def _signed_memory_bytes(self,prior):return mem
        def _token(self):return "synthetic-only-and-never-a-provider-key"
        def _exec(self,args,**kw):seen.append((args,kw))
        def _owned_or_absent(self,*,expected_memory_bytes):
            assert expected_memory_bytes==2*1024**3
            return {"Image":image,"State":{"Running":running}}
    class ShadowNames:
        SHADOW_PROJECT="jason-pmv4-shadow"
        SERVICE="pmv4-shadow-gateway"
    def need(ok,msg):
        if not ok:raise PermissionError(msg)
    ctx={"need":need,"ROLLBACK":r.PRIOR,"PRIOR_IMAGE":r.PRIOR_IMAGE,
         "docker_shadow":ShadowNames}
    exec(compile(method,"synthetic-reviewed-root","exec"),ctx)
    result=ctx["restore_prior_shadow_stopped"](Adapter(),tmp_path/root_name)
    return result,seen


def test_stopped_prior_restore_uses_one_explicit_compose_create_only(tmp_path):
    value,seen=run_pure_prior_stopped_callback(tmp_path)
    assert value is None
    assert len(seen)==2
    assert seen[0][0]==["/usr/bin/docker","image","inspect",r.PRIOR_IMAGE]
    assert seen[1][0]==[
        "/usr/bin/docker","compose","--project-name","jason-pmv4-shadow",
        "-f",str(tmp_path/"trusted-prior-compose.yml"),"create",
        "--force-recreate","--no-build","--pull","never",
        "pmv4-shadow-gateway",
    ]
    assert seen[1][1]["env"]["PMV4_SHADOW_IMAGE_SHA"]==r.PRIOR_IMAGE
    assert all("start" not in args and "restart" not in args
               and "up" not in args for args,kw in seen)


@pytest.mark.parametrize("why,kw,error",[
    ("unrelated",{"name":"f"*40},"ROLLBACK_RELEASE_NOT_EXACT"),
    ("other_image",{"image":"sha256:"+"e"*64},"PRIOR_IMAGE_NOT_PINNED"),
    ("wrong_mem",{"memory":4*1024**3},"PRIOR_MEMORY_NOT_SIGNED"),
    ("running",{"running":True},"STOPPED_PRIOR_ROLLBACK_NOT_VERIFIED"),
])
def test_stopped_prior_restoration_negative_paths(tmp_path,why,kw,error):
    with pytest.raises(PermissionError,match=error):
        run_pure_prior_stopped_callback(tmp_path,**kw)


def test_recovery_safety_does_not_allow_accepted_native_receipt_rewind():
    text=root_code()
    assert text.count("A1_V5_NATIVE_ACCEPTED_REQUIRES_ROOT_REVIEW")>=2
    assert text.count('get("state")=="accepted"')>=2
    assert 'elif args.recover_existing_owner:recover_exact_consumed_v5()' in text
    assert 'mode.add_argument("--recover-existing-owner",action="store_true")' in text
    assert 'A1_V5_RECOVERY_SIGNED_OWNER_MISMATCH' in text


def load_generated_reused_oci_predicate():
    """Exercise actual generated root predicate without privileged imports."""
    import ast
    root=root_code()
    tree=ast.parse(root)
    exact=next(node for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name=="reviewed_reused_shadow_image")
    func=ast.Module(body=[exact],type_ignores=[])
    def need(ok,code):
        if not ok:
            raise PermissionError(code)
    variables={
        "need":need,
        "IMAGE":r.PRIOR_IMAGE,
        "PRIOR_IMAGE":r.PRIOR_IMAGE,
        "ROLLBACK":r.PRIOR,
        "CANDIDATE":SHA,
        "Any":object,
    }
    exec(compile(func,"rendered-root-OCI-identity","exec"),variables)
    return variables["reviewed_reused_shadow_image"],root


def test_reused_shadow_image_accepts_only_prior_reviewed_source_revision():
    check,generated=load_generated_reused_oci_predicate()
    actual=[{"Id":r.PRIOR_IMAGE,"Config":{"Labels":{
        "com.aot.jason.component":"pmv4-shadow",
        "com.aot.jason.lifecycle":"preproduction-only",
        "com.aot.jason.production-core":"excluded",
        "com.aot.jason.provider-mutations":"disabled",
        "com.aot.jason.source_revision":r.PRIOR,
    }}}]
    assert check(actual) is None
    assert 'reviewed_reused_shadow_image(item)' in generated
    assert 'source_revision"]==CANDIDATE' not in generated


@pytest.mark.parametrize("section,key,changed",[
    ("labels","com.aot.jason.component","pmv4-production"),
    ("labels","com.aot.jason.lifecycle","production"),
    ("labels","com.aot.jason.production-core","included"),
    ("labels","com.aot.jason.provider-mutations","enabled"),
    ("labels","com.aot.jason.source_revision",SHA),
    ("labels","com.aot.jason.source_revision","f"*40),
    ("labels","com.aot.jason.source_revision","0"*40),
    ("image","Id","sha256:"+"e"*64),
])
def test_reused_image_rejects_any_changed_digest_or_security_label(section,key,changed):
    check,_=load_generated_reused_oci_predicate()
    actual=[{"Id":r.PRIOR_IMAGE,"Config":{"Labels":{
        "com.aot.jason.component":"pmv4-shadow",
        "com.aot.jason.lifecycle":"preproduction-only",
        "com.aot.jason.production-core":"excluded",
        "com.aot.jason.provider-mutations":"disabled",
        "com.aot.jason.source_revision":r.PRIOR,
    }}}]
    if section=="labels":
        actual[0]["Config"]["Labels"][key]=changed
    else:actual[0][key]=changed
    with pytest.raises(PermissionError,match="A1_SHADOW_IMAGE_NOT_REVIEWED"):
        check(actual)


@pytest.mark.parametrize("bad",[[],[None], [{}], [None,None], None,
                                [{"Config":{"Labels":None}}],
                                [{"Id":r.PRIOR_IMAGE,"Config":None}],
                                [{"Id":r.PRIOR_IMAGE,"Config":{"Labels":{}}}]])
def test_reused_image_rejects_missing_or_ambiguous_oci_inspection(bad):
    check,_=load_generated_reused_oci_predicate()
    with pytest.raises(PermissionError,match="A1_SHADOW_IMAGE_NOT_REVIEWED"):
        check(bad)


def test_generated_reused_image_is_not_arbitrary_allowlisted_prior():
    code=root_code()
    assert 'and IMAGE==PRIOR_IMAGE' in code
    assert 'and labels.get("com.aot.jason.source_revision")==ROLLBACK' in code
    assert 'and labels.get("com.aot.jason.provider-mutations")=="disabled"' in code
    assert 'and labels.get("com.aot.jason.production-core")=="excluded"' in code
    assert code.count('A1_SHADOW_IMAGE_NOT_REVIEWED')==2
