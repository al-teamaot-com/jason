"""Disposable UID0 filesystem installation, with Jason's real ownership topology.

These tests refuse to run on a host that already contains Jason directories.
They exercise production=True stagers, real file ownership/modes, signatures,
canonical imports, native manifest attestation and inert recovery. CI/source
and timer observations are explicit synthetic callbacks; no provider/systemd
operation, live credential or production acceptance is claimed.
"""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import base64
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel import signed_owner_release as signer
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_replacement_unit_bundle as units

pytestmark=pytest.mark.skipif(os.geteuid()!=0,reason="disposable UID0 filesystem only")
REPO=Path(__file__).resolve().parents[2]
BASE=Path("/usr/local/lib/jason/pmv4-e-bootstrap")
TRUST=BASE/"trusted"
SOURCE=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
ROOT=Path("/var/lib/jason/independent-component-release")
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
SHARED_SOURCE="17d616943b72363fe35554d5eaa583850a707a5c"
ROOTS=tuple(map(Path,["/opt/jason","/usr/local/lib/jason","/var/lib/jason",
                     "/etc/jason-owner-release","/etc/jason","/srv/jason","/home/al"]))

def put(path,raw,mode=0o444,uid=0):
    path=Path(path)
    missing=[];parent=path.parent
    while not parent.exists():
        missing.append(parent);parent=parent.parent
    path.parent.mkdir(parents=True,exist_ok=True)
    for directory in missing:
        os.chown(directory,0,0);directory.chmod(0o755)
    path.write_bytes(raw)
    path.chmod(mode)
    os.chown(path,uid,uid)

def git_blob(revision,name):
    return subprocess.check_output(["git","-c","safe.directory="+str(REPO),
        "-C",str(REPO),"show",revision+":"+name])

def child(script,*args):
    result=subprocess.run([sys.executable,"-I","-B","-c",script,*map(str,args)],
        cwd="/",capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+"\n"+result.stderr
    return result.stdout

@pytest.fixture(scope="module")
def identity_alias():
    added_user=added_group=False
    try:
        try:
            assert pwd.getpwnam("al").pw_uid==1000
        except KeyError:
            try:grp.getgrgid(1000)
            except KeyError:
                subprocess.run(["groupadd","--gid","1000","pmv4-lab-al"],check=True,capture_output=True)
                added_group=True
            subprocess.run(["useradd","--non-unique","--uid","1000","--gid","1000",
                            "--no-user-group","--no-create-home","al"],check=True,capture_output=True)
            added_user=True
        yield
    finally:
        if added_user:subprocess.run(["userdel","al"],check=True,capture_output=True)
        if added_group:subprocess.run(["groupdel","pmv4-lab-al"],check=True,capture_output=True)

@pytest.fixture
def filesystem(tmp_path,identity_alias):
    assert all(not p.exists() for p in ROOTS),"Refusing existing Jason filesystem"
    previous_umask=os.umask(0o022)
    try:
        for root in ROOTS:
            root.mkdir(parents=True,exist_ok=True)
            os.chown(root,0,0);root.chmod(0o755)
        os.chown("/var/lib/jason",1000,1000)
        Path("/var/lib/jason").chmod(0o750)
        os.chown("/opt/jason",997,984)
        Path("/opt/jason").chmod(0o750)
        for name in packet.REVIEWED_PATHS:
            put(TRUST/name,(REPO/name).read_bytes())
            put(SOURCE/name,(REPO/name).read_bytes(),uid=1000)
        for p in TRUST.rglob("*"):
            if p.is_dir():p.chmod(0o555)
        TRUST.chmod(0o555)
        for parent in SOURCE.parents:
            if str(parent).startswith("/srv/jason"):parent.chmod(0o755)
        subprocess.run(["git","-c","core.hooksPath=/dev/null","init",str(SOURCE)],
                       check=True,capture_output=True)
        commands=[
            ["add","."],["-c","user.name=Filesystem Lab","-c",
            "user.email=filesystem@example.invalid","-c","core.hooksPath=/dev/null",
            "commit","-m","synthetic reviewed filesystem source"],
        ]
        for command in commands:
            subprocess.run(["git","-c","safe.directory="+str(SOURCE),"-C",str(SOURCE),
                            *command],check=True,capture_output=True)
        candidate=subprocess.check_output(["git","-c","safe.directory="+str(SOURCE),
            "-C",str(SOURCE),"rev-parse","HEAD"],text=True).strip()
        for p in SOURCE.rglob("*"):os.chown(p,1000,1000)
        os.chown(SOURCE,1000,1000);SOURCE.chmod(0o700)
        original=Path("/opt/jason/independent-component-release/trusted")
        for name in packet.ROOT_COMPONENTS_PREINSTALLED:
            put(original/name,(REPO/name).read_bytes())
        for directory in (original,original/"tools",original/"implementation",original/"implementation/kernel"):
            directory.chmod(0o555)
        for folder in [ROOT,ROOT/"receipts",ROOT/"stage-e-bootstrap",ROOT/"releases"]:
            folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o700)
        (BASE/"releases").mkdir(mode=0o755)
        for name in ("stage-e-code-before","stage-e-physical-before","stage-e-step-audit"):
            (ROOT/name).mkdir(mode=0o700)
        unit_dir=Path("/home/al/.config/systemd/user")
        unit_dir.mkdir(parents=True);unit_dir.chmod(0o700);os.chown(unit_dir,1000,1000)
        assert not list(Path("/etc/systemd/system").glob("jason-pmv4-*"))
        for relative in ["tools/jason_self_heal_watchdog.py","tools/release_manager_host_runner.py"]:
            mode=0o700 if relative.endswith("watchdog.py") else 0o755
            put(Path("/home/al/.local/lib/jason")/Path(relative).name,
                git_blob(LKG,relative),mode,1000)
        put("/usr/local/lib/jason/release_host_reconcile_worker.py",
            git_blob(SHARED_SOURCE,"tools/release_host_reconcile_worker.py"),0o755)
        live=(REPO/"tools/tests/fixtures/pmv4_e_root_policy_after_scoped_backport.json").read_bytes()
        put("/etc/jason/release-readback-recovery/production-desired-state.json",live,0o600)
        shared_sha=sha256(Path("/usr/local/lib/jason/release_host_reconcile_worker.py").read_bytes()).hexdigest()
        put("/etc/jason-owner-release/catalog-scoped-promotion-installed.json",
            json.dumps({"root_worker_sha256":shared_sha}).encode(),0o600)
        private=Ed25519PrivateKey.generate()
        public=private.public_key()
        raw=public.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        pub={
            "schema_version":"1.0","authorization":"authenticated_entra_owner_exact_release",
            "organization_id":"aot","tenant_id":signer.TID,
            "authorized_owner_subjects":[{"owner_oid":oid,"owner_principal":principal}
                for oid,principal in sorted(signer.EXACT_OWNER_OAUTH_SUBJECTS.items())],
            "public_key_base64":base64.b64encode(raw).decode(),
            "public_key_sha256":signer.public_key_sha256(public),"standing_authority":False,
        }
        put("/etc/jason-owner-release/verified-owner-public-key.json",
            json.dumps(pub).encode(),0o644)
        put("/usr/local/lib/jason/owner_signed_release.py",
            (REPO/"implementation/kernel/signed_owner_release.py").read_bytes(),0o644)
        review=contract.draft(candidate_sha=candidate,rollback_sha=LKG)
        proof=signer.issue_exact_owner_release(
            approval_id="owner-mcp-"+"7"*32,release_id="release-"+candidate[:16],
            candidate_sha=candidate,rollback_sha=LKG,
            scope_sha256=review["manifest"]["source_scope_sha256"],
            manifest_sha256=review["manifest_sha256"],
            freeze_sha256=packet.EXPECTED_FREEZE,
            verified_tenant_id=signer.TID,verified_owner_oid=signer.OWNER_OID,
            verified_principal=signer.OWNER_PRINCIPAL,verified_organization_id="aot",
            confirmed_decision="approve",at=datetime.now(timezone.utc),private_key=private)
        request={"schema_version":"1.0","action":"pmv4_e_stage_exact_signed_inert_root_v1",
            "request_id":"release-"+candidate[:16],"candidate_sha":candidate,
            "rollback_sha":LKG,"scope_sha256":review["manifest"]["source_scope_sha256"],
            "manifest_sha256":review["manifest_sha256"],
            "freeze_sha256":packet.EXPECTED_FREEZE,"signed_owner_proof":proof}
        request_path=tmp_path/"synthetic-request.json"
        request_path.write_text(json.dumps(request))
        yield candidate,request_path,private
    finally:
        for name,data in units.generate(base=REPO).items():
            if Path(name).parts[-2]=="system":
                target=Path("/etc/systemd/system")/Path(name).name
                if target.exists():
                    assert target.read_bytes()==data,"Refusing foreign system unit cleanup"
                    target.unlink()
        for root in reversed(ROOTS):
            if root.exists():shutil.rmtree(root)
        os.umask(previous_umask)

STAGE=r"""
import importlib.util,json,sys
from pathlib import Path
entry=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_root_bootstrap_once.py")
spec=importlib.util.spec_from_file_location("canonical_bootstrap",entry)
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
for directory in (b.TRUST,b.NATIVE):
    meta=directory.lstat()
    assert (meta.st_uid,meta.st_gid,meta.st_mode&0o022)==(0,0,0),str(directory)+str((meta.st_uid,meta.st_gid,oct(meta.st_mode)))
b.bind_original_native()
from tools import pmv4_e_installation_preflight as preflight
from tools import pmv4_e_signed_bootstrap_phase as signed
from tools import pmv4_e_immutable_source_stage as immutable
from tools import pmv4_e_root_trust_stage as trust
from tools import pmv4_e_native_release_contract as contract
candidate=sys.argv[1];request=json.loads(Path(sys.argv[2]).read_bytes())
print(json.dumps(preflight.collect(candidate,require_layout=True)))
review=contract.draft(candidate_sha=candidate,rollback_sha=request["rollback_sha"],source_root=b.TRUST)
phase=signed.SignedInertBootstrap(
    source_root=b.TRUST,host_lock_held=lambda:True,freeze_lock_held=lambda:True,
    legacy_active=lambda:True,replacements_inert=lambda:True,marker_absent=lambda:True,
    source_ci_verified=lambda sha:sha==candidate,production=True)
phase.begin(request)
verified=lambda:phase.signed_started(candidate_sha=candidate,
    scope_sha256=request["scope_sha256"],
    approval_id=request["signed_owner_proof"]["payload"]["approval_id"])
source=immutable.ImmutableRootSourceStage(
    exact_owner_verified=verified,original_host_locked=lambda:True,
    original_freeze_locked=lambda:True,marker_absent=lambda:True,
    replacement_inert=lambda:True,production=True)
hashes=review["source_scope"]["exact_replacement_files_sha256"]
source.stage(candidate=candidate,exact_hashes=hashes)
root=trust.RootTrustStager(
    source=b.RELEASES/candidate,native_signed_started=verified,native_host_locked=lambda:True,
    native_freeze_locked=lambda:True,native_marker_absent=lambda:True,
    native_replacements_inert=lambda:True,production=True)
root.stage(source_sha=candidate,exact_hashes=hashes)
b.safe_release_records(candidate,review,__import__("tools.pmv4_e_exact_release_packet",fromlist=["canonical"]))
print("production_mode_source_and_trust_staged")
"""
ATTEST=r"""
import importlib.util,json,sys
from pathlib import Path
entry=Path("/usr/local/lib/jason/pmv4-e-bootstrap/native/tools/pmv4_e_native_root_entry.py")
spec=importlib.util.spec_from_file_location("canonical_native_entry",entry)
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
manifest,scope=e.installed_release(sys.argv[1])
e.bind_original_native_packages(scope)
from tools import pmv4_e_native_root_manifest_attestation as attestor
result=attestor.inspect(release_dir=e.NATIVE_ROOT/"releases"/sys.argv[1],production=True)
assert result["status"]=="root_source_attested_no_release_authority"
assert e.PRODUCTION_RELEASE_ROOT==Path("/usr/local/lib/jason/pmv4-e-bootstrap/releases")
from tools import pmv4_e_exact_code_transaction as code
from tools import pmv4_e_replacement_unit_bundle as units
from tools import pmv4_e_systemd_root_ops as systemd
from types import SimpleNamespace
before={name:path.read_bytes() for name,path in code.DEFAULT_TARGETS.items()}
tx=code.StageECodeTransaction(signed_started=lambda:True,
 shared_host_lock=lambda:True,freeze_lock=lambda:True,
 replacement_marker_absent=lambda:True,production=True)
tx.prepare(candidate=sys.argv[1],scope=scope)
tx.apply(candidate=sys.argv[1],scope=scope)
tx.verify(candidate=sys.argv[1],scope=scope)
tx.restore(candidate=sys.argv[1],scope=scope)
assert before=={name:path.read_bytes() for name,path in code.DEFAULT_TARGETS.items()}
surface=systemd.ExactSystemdSurface(
 runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout=""),production=True)
hashes={name:__import__("hashlib").sha256(raw).hexdigest()
 for name,raw in units.generate(base=e.TRUST).items()}
created=surface.stage(hashes)
assert len(created)==12 and all(Path(path).stat().st_uid==0 for path in created)
surface.unstage_exact(hashes)
assert not any(Path(path).exists() for path in created)
print("production_mode_code_policy_and_twelve_unit_files_verified")
print(json.dumps(result))
"""
CLEAN=r"""
import importlib.util,json,sys
from pathlib import Path
entry=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_root_bootstrap_once.py")
spec=importlib.util.spec_from_file_location("canonical_bootstrap",entry)
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.bind_original_native()
from tools import pmv4_e_signed_bootstrap_phase as signed
from tools import pmv4_e_immutable_source_stage as immutable
from tools import pmv4_e_root_trust_stage as trust
from tools import pmv4_e_native_release_contract as contract
candidate=sys.argv[1];request=json.loads(Path(sys.argv[2]).read_bytes())
review=contract.draft(candidate_sha=candidate,rollback_sha=request["rollback_sha"],source_root=b.TRUST)
phase=signed.SignedInertBootstrap(
 source_root=b.TRUST,host_lock_held=lambda:True,freeze_lock_held=lambda:True,
 legacy_active=lambda:True,replacements_inert=lambda:True,marker_absent=lambda:True,
 source_ci_verified=lambda sha:sha==candidate,production=True)
verified=lambda:phase.signed_started(candidate_sha=candidate,
 scope_sha256=request["scope_sha256"],approval_id=request["signed_owner_proof"]["payload"]["approval_id"])
root=trust.RootTrustStager(source=b.RELEASES/candidate,
 native_signed_started=verified,native_host_locked=lambda:True,native_freeze_locked=lambda:True,
 native_marker_absent=lambda:True,native_replacements_inert=lambda:True,production=True)
hashes=review["source_scope"]["exact_replacement_files_sha256"]
root.recover_inert_stage(hashes)
source=immutable.ImmutableRootSourceStage(exact_owner_verified=verified,
 original_host_locked=lambda:True,original_freeze_locked=lambda:True,
 marker_absent=lambda:True,replacement_inert=lambda:True,production=True)
source.recover_inert(candidate=candidate,exact_hashes=hashes)
try:phase.begin(request)
except PermissionError as exc:assert "ONE_USE_REPLAY" in str(exc)
else:raise AssertionError("consumed bootstrap proof was replayed")
print("production_mode_inert_cleanup_and_replay_denial_verified")
"""

def test_real_canonical_staging_attestation_and_cleanup_with_service_owned_opt(filesystem):
    candidate,request,_=filesystem
    original=Path("/opt/jason").stat()
    assert (original.st_uid,original.st_gid,original.st_mode&0o777)==(997,984,0o750)
    assert "production_mode_source_and_trust_staged" in child(STAGE,candidate,request)
    assert (BASE/"native").is_dir() and (BASE/"releases"/candidate).is_dir()
    assert "root_source_attested_no_release_authority" in child(ATTEST,candidate)
    assert "cleanup_and_replay_denial_verified" in child(CLEAN,candidate,request)
    assert not (BASE/"native").exists() and not (BASE/"releases"/candidate).exists()
    current=Path("/opt/jason").stat()
    assert (current.st_uid,current.st_gid,current.st_mode)==(
        original.st_uid,original.st_gid,original.st_mode)

@pytest.mark.parametrize("fault",["source_bytes","native_parent_owner","release_parent_owner"])
def test_installation_faults_deny_before_consuming_bootstrap_approval(filesystem,fault):
    candidate,request,_=filesystem
    if fault=="source_bytes":
        (SOURCE/"tools/pmv4_e_unit_admission.py").chmod(0o644)
        (SOURCE/"tools/pmv4_e_unit_admission.py").write_text("stale checkout")
    else:
        target=BASE if fault=="native_parent_owner" else BASE/"releases"
        os.chown(target,997,984)
    script=r"""
import sys
sys.path.insert(0,"/usr/local/lib/jason/pmv4-e-bootstrap/trusted")
from tools import pmv4_e_installation_preflight as preflight
try:preflight.collect(sys.argv[1],require_layout=True)
except PermissionError:print("denied_before_approval")
else:raise AssertionError("unsafe installation preflight accepted")
"""
    assert "denied_before_approval" in child(script,candidate)
    assert not list((ROOT/"stage-e-bootstrap").iterdir())
    assert not (BASE/"native").exists()


@pytest.mark.parametrize("fault",[None,"signature","native_receipt"])
def test_historical_installation_evidence_is_verified_and_never_reissues_authority(
        filesystem,monkeypatch,fault):
    from tools import pmv4_e_dispatch_install as install
    _,_,private=filesystem
    candidate=install.INSTALLED_ISOLATED_CANDIDATE
    policy={"candidate_sha":candidate,"scope_sha256":"1"*64,"manifest_sha256":"2"*64,
            "freeze_sha256":packet.EXPECTED_FREEZE}
    scope={"policy":policy,"action":"historical-exact-installation-only"}
    monkeypatch.setattr(install,"INSTALLED_ISOLATED_SCOPE",
                        install.digest(install.canonical(scope)))
    prior=BASE/("isolated-cutover-"+candidate);prior.mkdir(mode=0o700)
    put(prior/"approval.json",install.canonical({
        "scope":scope,"owner_object_id":signer.OWNER_OID}),0o400)
    issued=datetime.now(timezone.utc)-timedelta(days=2)
    proof=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+"8"*32,release_id="release-"+candidate[:16],
        candidate_sha=candidate,rollback_sha=LKG,scope_sha256=policy["scope_sha256"],
        manifest_sha256=policy["manifest_sha256"],freeze_sha256=packet.EXPECTED_FREEZE,
        verified_tenant_id=signer.TID,verified_owner_oid=signer.OWNER_OID,
        verified_principal=signer.OWNER_PRINCIPAL,verified_organization_id="aot",
        confirmed_decision="approve",at=issued,private_key=private)
    if fault=="signature":proof["payload"]["scope_sha256"]="3"*64
    put(prior/"owner-proof.json",install.canonical({"signed_owner_proof":proof}),0o400)
    put(ROOT/"stage-e-bootstrap"/("owner-"+proof["payload"]["approval_id"]+".json"),
        install.canonical({"signed_owner_proof":proof,"candidate_sha":candidate,
         "no_unit_mutations":True,"started_at":(issued+timedelta(seconds=1)).isoformat()}),0o600)
    if fault=="native_receipt":
        put(ROOT/"receipts"/"owner-native.json",
            json.dumps({"candidate_sha":candidate,"state":"started"}).encode(),0o600)
    journal_before=list((ROOT/"stage-e-bootstrap").iterdir())
    if fault:
        with pytest.raises(PermissionError):
            install.verified_previous_isolated_install(install.canonical(policy))
    else:
        assert install.verified_previous_isolated_install(install.canonical(policy)) is None
    assert list((ROOT/"stage-e-bootstrap").iterdir())==journal_before
    assert not (BASE/"native").exists()
