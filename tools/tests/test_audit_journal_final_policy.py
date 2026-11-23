"""The timer can become required only after its genuine activation."""
from types import SimpleNamespace
import pytest
from tools import audit_journal_release_executor as release
from tools import audit_journal_release_scope as scope
from orchestrator.segmented_journal import JournalUnavailable


@pytest.mark.parametrize("fault",[None,"inactive","disabled","unknown_policy","changed_final"])
def test_ready_policy_is_bound_to_real_timer_and_native_revalidation(monkeypatch,fault):
 initial={"stage":"initial"};final={"stage":"ready"};writes=[];events=[]
 executor=object.__new__(release.ExactRelease)
 executor.c=SimpleNamespace(_json=lambda path,row,mode:writes.append((path,row,mode)))
 executor.plan={"scope":{"desired_state_initial_sha256":release.digest(initial),"desired_state_after_sha256":release.digest(final)}}
 executor.revalidate=lambda:events.append("guarded_native_revalidation")
 def read(path,uid,mode):
  if path==release.PRIVATE/"desired-final.json":return {"stage":"wrong"} if fault=="changed_final" else final
  return {"stage":"unknown"} if fault=="unknown_policy" else initial
 def run(argv,**kwargs):
  if argv[1]=="show":return SimpleNamespace(returncode=0,stdout="ActiveState="+("inactive" if fault=="inactive" else "active")+"\nUnitFileState="+("disabled" if fault=="disabled" else "enabled"))
  assert argv==["/usr/bin/systemctl","start","jason-production-drift-watchdog.service"]
  events.append("real_native_drift");return SimpleNamespace(returncode=0)
 monkeypatch.setattr(release,"read_control",read);monkeypatch.setattr(release.subprocess,"run",run)
 if fault is None:
  executor.finalize_desired()
  assert writes==[(scope.DESIRED,final,0o600)] and events==["real_native_drift","guarded_native_revalidation"]
 else:
  with pytest.raises(JournalUnavailable):executor.finalize_desired()
  assert writes==[] and events==[]
