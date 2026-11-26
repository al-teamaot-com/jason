"""Exercise actual preflight with the native directory guard before data access."""
from pathlib import Path
from types import SimpleNamespace
import stat
import pytest
from tools import audit_journal_install as install
from tools import pmv4_e_operational_closure as native

class DataAdmissionReached(Exception):
    pass

class ObservedDirectory:
    def __init__(self, path, row):
        self.name=path.name
        self.row=row
    def lstat(self):
        return SimpleNamespace(st_uid=self.row[0],st_gid=self.row[1],
                               st_mode=stat.S_IFDIR|self.row[2])
    def is_symlink(self):
        return self.row[3]

def prepare(monkeypatch):
    # Unit tests isolate mount-namespace admission. The native UID0 fixture
    # exercises the real namespace check and filesystem metadata separately.
    def test_path(name):
        if str(name) in ("/proc/self/ns/mnt","/proc/1/ns/mnt"):
            return SimpleNamespace(stat=lambda:SimpleNamespace(st_ino=7))
        return Path(name)
    monkeypatch.setattr(install,"Path",test_path)
    paths=("/usr/local/lib/jason","/etc/jason-owner-release",
           "/etc/systemd/system","/var/lib","/srv","/srv/jason")
    rows={Path(name):[0,0,0o755,False] for name in paths}
    rows[Path("/var/lib/jason")]=[1000,1000,0o750,False]
    reached=[]
    def stop(_):
        reached.append(True)
        raise DataAdmissionReached
    monkeypatch.setattr(install,"capacity",stop)
    def guard(path,uid,mode=None):
        native.directory(ObservedDirectory(path,rows[path]),uid,mode)
    return rows,reached,{"directory":guard}

def invoke(c):
    install.inspect(SimpleNamespace(),None,None,"a"*40,{},c)

def test_service_data_parent_reaches_data_admission_without_metadata_changes(monkeypatch):
    rows,reached,c=prepare(monkeypatch)
    before={path:row[:] for path,row in rows.items()}
    with pytest.raises(DataAdmissionReached):invoke(c)
    assert reached==[True] and rows==before

@pytest.mark.parametrize("owner,group,mode,link",[
    (0,0,0o750,False),
    (1001,1000,0o750,False),
    (1000,984,0o750,False),
    (1000,1000,0o770,False),
    (1000,1000,0o752,False),
    (1000,1000,0o755,False),
    (1000,1000,0o750,True),
])
def test_wrong_service_parent_custody_denies_before_data_or_owner_access(
        monkeypatch,owner,group,mode,link):
    rows,reached,c=prepare(monkeypatch)
    rows[Path("/var/lib/jason")]=[owner,group,mode,link]
    with pytest.raises(native.ClosureDenied,match="DIRECTORY_IDENTITY"):invoke(c)
    assert reached==[]

@pytest.mark.parametrize("path",[
    "/usr/local/lib/jason","/etc/jason-owner-release",
    "/etc/systemd/system","/var/lib","/srv","/srv/jason",
])
@pytest.mark.parametrize("owner,group,mode,link",[
    (1000,1000,0o755,False),(0,1000,0o755,False),
    (0,0,0o775,False),(0,0,0o755,True),
])
def test_root_installation_parents_remain_root_controlled(
        monkeypatch,path,owner,group,mode,link):
    rows,reached,c=prepare(monkeypatch)
    rows[Path(path)]=[owner,group,mode,link]
    with pytest.raises(native.ClosureDenied,match="DIRECTORY_IDENTITY"):invoke(c)
    assert reached==[]
