"""Do not reset a collected inactive unit; preserve bounded useful diagnostics."""
from types import SimpleNamespace
import pytest
from tools import audit_journal_pre_cutover_repair as repair
from tools import audit_journal_install as install


@pytest.mark.parametrize("state,pid",[("inactive","0"),("failed","0"),("active","12"),("activating","0"),("deactivating","0"),("failed","12")])
def test_reset_only_stopped_actual_failure(state,pid):
 calls=[]
 def command(argv,**kwargs):
  calls.append(argv)
  if argv[1]=="show":return "ActiveState="+state+"\nMainPID="+pid
  assert argv==["/usr/bin/systemctl","reset-failed","jason-audit-journal-release.service"]
  return ""
 I=SimpleNamespace(command=command)
 if state in ("inactive","failed") and pid=="0":
  repair.reset_failed_worker(I)
  assert len(calls)==(2 if state=="failed" else 1)
 else:
  with pytest.raises(PermissionError):repair.reset_failed_worker(I)
  assert len(calls)==1


def test_command_denial_identifies_operation_without_private_output(monkeypatch):
 secret="fixture-secret-never-print"
 result=SimpleNamespace(returncode=1,stdout=secret,stderr="Unit jason-audit-journal-release.service not loaded. "+secret)
 monkeypatch.setattr(install.subprocess,"run",lambda *args,**kwargs:result)
 with pytest.raises(PermissionError) as failure:
  install.command(["/usr/bin/systemctl","reset-failed","jason-audit-journal-release.service",secret])
 rendered=install.denial_text(failure.value)
 assert all(v in rendered for v in ("exe=systemctl","operation=reset-failed","unit=jason-audit-journal-release.service","exit=1","reason=unit_not_loaded"))
 assert secret not in rendered


def test_unrelated_errors_retain_existing_private_detail_boundary():
 assert install.denial_text(PermissionError("JOURNAL_CONTEXT_REPAIR_DENIED:fixture-secret"))=="JOURNAL_CONTEXT_REPAIR_DENIED"
