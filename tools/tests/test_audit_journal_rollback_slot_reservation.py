"""Test exact native retention and archive-before-remove without real Docker."""
import copy,io,json,os,tarfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_rollback_slot_reservation as r
from tools import audit_journal_release_scope as s
from tools import audit_journal_container_release as eng

POLICY={"max_stopped_rollback_containers":27,"rollback_container_prefixes":[
    "jason-runtime-rollback-","jason-mcp-pilot-rollback-","jason-mcp-rollback-",
    "jason-teams-gateway-rollback-","jason-pmv4-ticket-core-rollback-audit-"]}
CANDIDATE="a"*40
SCOPE="b"*64

class Docker:
    def __init__(self):
        self.names=[r.NAME,r.SIBLING,
                    "jason-mcp-rollback-constant-contact-oauth-20261112",
                    "jason-mcp-rollback-pmv4-a0-issuer",
                    "jason-pmv4-ticket-core-rollback-audit-before-20b32548402d"]
        self.names += ["jason-runtime-rollback-old-%02d"%i for i in range(17)]
        self.rows={r.ID:r.NAME,r.SIBLING_ID:r.SIBLING}
        self.rows.update({("%064x"%(i+10)):n for i,n in enumerate(self.names) if n not in (r.NAME,r.SIBLING)})
        self.inspect={}
        for ident,name in ((r.ID,r.NAME),(r.SIBLING_ID,r.SIBLING)):
            self.inspect[ident]={"Id":ident,"Name":"/"+name,"Image":r.IMAGE,
                "State":{"Status":"exited","Running":False,"Pid":0},
                "Config":{"Labels":{"com.teamaot.jason.source_revision":r.REVISION}},
                "HostConfig":{"AutoRemove":False},"Mounts":[{"Type":"bind"}],
                "SizeRootFs":249016320,"SizeRw":131072}
        self.removed=[]
        self.before_remove=lambda:None
    def command(self,argv):
        assert argv[0]==r.DOCKER
        if argv[1:3]==["ps","-a"]:
            if "--filter" in argv:return "\n".join(self.names)
            return "\n".join(ident+"|"+name for ident,name in self.rows.items())
        if argv[1]=="inspect":return json.dumps([self.inspect[argv[-1]]])
        if argv[1:3]==["image","inspect"]:return r.IMAGE
        if argv[1]=="rm":
            assert argv==[r.DOCKER,"rm",r.ID]
            self.before_remove()
            self.removed.append(r.ID)
            self.names.remove(r.NAME);del self.rows[r.ID]
            return r.ID
        pytest.fail("Unexpected Docker call")

def test_native_counts_older_mcp_and_reserves_exact_one_slot():
    engine=Docker()
    slots=r.plan_capacity(engine,s,eng,POLICY)
    assert slots["count"]==22 and slots["new_release_slots_after"]==27
    assert len(slots["after_stopped_names"])==21
    assert set(slots["stopped_names"])-set(slots["after_stopped_names"])=={r.NAME}
    assert slots["retirement"]["id"]==r.ID
    assert slots["retirement"]["retained_sibling_id"]==r.SIBLING_ID
    assert engine.removed==[]
    engine.names.remove("jason-runtime-rollback-old-00")
    assert r.plan_capacity(engine,s,eng,POLICY)["retirement"] is None

@pytest.mark.parametrize("fault",["extra","wrong_target","wrong_sibling","running","volume","image","limit"])
def test_native_reservation_never_widens_limit_or_substitutes_retirement(fault):
    engine=Docker();policy=copy.deepcopy(POLICY)
    if fault=="extra":engine.names.append("jason-mcp-rollback-extra")
    if fault=="wrong_target":engine.names[0]="jason-runtime-rollback-other"
    if fault=="wrong_sibling":engine.names[1]="jason-runtime-rollback-other"
    if fault=="running":engine.inspect[r.ID]["State"]["Running"]=True
    if fault=="volume":engine.inspect[r.ID]["Mounts"]=[{"Type":"volume"}]
    if fault=="image":engine.inspect[r.SIBLING_ID]["Image"]="wrong"
    if fault=="limit":policy["max_stopped_rollback_containers"]=28
    with pytest.raises(PermissionError):r.plan_capacity(engine,s,eng,policy)
    assert engine.removed==[]

@pytest.fixture
def archive_fixture(monkeypatch,tmp_path):
    root=tmp_path/"archive";root.mkdir()
    ledger=tmp_path/"ledger";ledger.mkdir()
    fake_s=SimpleNamespace(ARCHIVE=tmp_path)
    engine=Docker()
    slots=r.plan_capacity(engine,s,eng,POLICY)
    monkeypatch.setattr(r,"_archive_dirs",lambda *a,**k:root)
    # Real tar parsing, with local fixture files standing in for Root custody.
    class OS:
        def __getattr__(self,key):return getattr(os,key)
        def geteuid(self):return 0
        def fstat(self,fd):
            m=os.fstat(fd)
            return SimpleNamespace(st_mode=m.st_mode,st_uid=0,st_gid=0,
                                   st_nlink=m.st_nlink,st_size=m.st_size)
    monkeypatch.setattr(r,"os",OS())
    def atomic(path,raw,mode):
        Path(path).write_bytes(raw);Path(path).chmod(mode)
    monkeypatch.setattr(r.tx,"atomic",atomic)
    monkeypatch.setattr(r.tx,"raw_file",lambda path,mode:Path(path).read_bytes())
    monkeypatch.setattr(r.tx,"sync",lambda path:None)
    def export(argv,*,stdout,**kwargs):
        assert argv[-3:]==[r.DOCKER,"export",r.ID]
        assert argv[0]=="/usr/bin/prlimit"
        with tarfile.open(fileobj=stdout,mode="w|") as archive:
            data=b"fixture rootfs";entry=tarfile.TarInfo("fixture")
            entry.size=len(data);archive.addfile(entry,io.BytesIO(data))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(r.subprocess,"run",export)
    return engine,slots,fake_s,root,ledger

def test_verified_archive_precedes_exact_removal_and_resume_is_idempotent(archive_fixture):
    engine,slots,fake_s,root,ledger=archive_fixture
    def before_remove():
        assert (ledger/"retirement-archive.json").is_file()
        proof=json.loads((ledger/"retirement-archive.json").read_bytes())
        assert r._tar_proof(root/"rootfs.tar")==proof["rootfs"]
        assert (root/"container-inspect.json").is_file()
    engine.before_remove=before_remove
    r.apply(engine,fake_s,CANDIDATE,ledger,SCOPE,slots)
    assert engine.removed==[r.ID] and r.SIBLING_ID in engine.rows
    assert r.plan_capacity(engine,s,eng,POLICY,approved=slots,retirement_verified=True)==slots
    r.apply(engine,fake_s,CANDIDATE,ledger,SCOPE,slots)
    assert engine.removed==[r.ID]
    assert json.loads((ledger/"retirement-result.json").read_bytes())["status"]=="retired_and_archive_verified"

def test_export_failure_never_removes_container(archive_fixture,monkeypatch):
    engine,slots,fake_s,root,ledger=archive_fixture
    monkeypatch.setattr(r.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=1))
    with pytest.raises(PermissionError,match="ROOTFS_EXPORT_FAILED"):
        r.apply(engine,fake_s,CANDIDATE,ledger,SCOPE,slots)
    assert engine.removed==[] and not (ledger/"retirement-archive.json").exists()

def test_tampered_archive_denies_same_grant_resume(archive_fixture):
    engine,slots,fake_s,root,ledger=archive_fixture
    r.apply(engine,fake_s,CANDIDATE,ledger,SCOPE,slots)
    path=root/"container-inspect.json";path.chmod(0o600);path.write_bytes(b"{}");path.chmod(0o400)
    with pytest.raises(PermissionError,match="ARCHIVE_METADATA_CHANGED"):
        r.verified_absence(engine,fake_s,CANDIDATE,ledger,SCOPE,slots["retirement"])
    assert engine.removed==[r.ID]
