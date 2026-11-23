"""Fixed UID handoff retains privilege separation without PAM session policy."""
from types import SimpleNamespace
import pytest
from tools import audit_journal_control as control
from tools import audit_journal_release_executor as release
from orchestrator.segmented_journal import JournalUnavailable


def controller(monkeypatch,*,root=True,uid=1000):
 c=object.__new__(control.JournalController);c.p=SimpleNamespace(writer_uid=uid);c.fixture=False
 monkeypatch.setattr(control.os,"geteuid",lambda:0 if root else 1000)
 return c


@pytest.mark.parametrize("root,uid",[(False,1000),(True,1001),(True,0)])
def test_handoff_needs_root_and_exact_service_uid(monkeypatch,root,uid):
 c=controller(monkeypatch,root=root,uid=uid)
 with pytest.raises(JournalUnavailable,match="WRITER_IDENTITY"):c.writer_identity()


def test_fixed_identity_excludes_parent_secrets_and_supplementary_privileges(monkeypatch):
 c=controller(monkeypatch);monkeypatch.setenv("FIXTURE_ROOT_SECRET","must-not-reach-child")
 identity=c.writer_identity()
 assert identity["user"]==identity["group"]==1000 and identity["extra_groups"]==()
 assert identity["env"]=={"PATH":"/usr/bin:/bin","HOME":"/home/al","USER":"al","LOGNAME":"al","LANG":"C.UTF-8"}
 assert "FIXTURE_ROOT_SECRET" not in identity["env"]


def test_sql_child_is_isolated_fixed_uid_and_tracked_process_group(monkeypatch):
 c=controller(monkeypatch);seen=[]
 class Child:
  returncode=0
  def __init__(self,argv,**kwargs):seen.append((argv,kwargs))
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def communicate(self,timeout):return ('{"watermark":7}',"")
 monkeypatch.setattr(control.subprocess,"Popen",Child)
 result=c._sql("state",{"path":"/fixture/active.sqlite3"},seconds=5)
 assert result=={"watermark":7}
 argv,kw=seen[0]
 assert argv[:3]==["/usr/bin/python3","-I","-B"] and "/usr/sbin/runuser" not in argv
 assert str(control.ENTRY) in argv and argv[-3]=="state"
 assert kw["user"]==kw["group"]==1000 and kw["extra_groups"]==() and kw["start_new_session"] is True


def test_native_revalidation_uses_same_fixed_identity(monkeypatch):
 c=controller(monkeypatch);executor=object.__new__(release.ExactRelease);executor.c=c
 executor.status=lambda *args,**kwargs:None;seen=[]
 def run(argv,**kwargs):seen.append((argv,kwargs));return SimpleNamespace(returncode=0)
 monkeypatch.setattr(release.subprocess,"run",run)
 executor.native()
 assert len(seen)==4 and all(argv[0]=="/usr/bin/systemctl" for argv,_ in seen[:3])
 argv,kw=seen[-1]
 assert argv[:3]==["/usr/bin/python3","-B","-c"]
 assert kw["user"]==kw["group"]==1000 and kw["extra_groups"]==()
 assert "request_root_control_transition" in argv[-1]
