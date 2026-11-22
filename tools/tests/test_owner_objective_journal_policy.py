"""Exact accepted data-policy inheritance; no production files are read."""
from hashlib import sha256
from pathlib import Path
import copy,json
import pytest
from tools import owner_objective_install as install

def raw(value):return install.canonical(value)
def h(value):return sha256(value).hexdigest()

def fixture(outcome="accepted"):
 legacy=h(b"legacy-policy")
 candidate="a"*40;current=raw({"fixture":"accepted policy "+outcome})
 sources={"tools/fixture_"+str(n)+".py":h(("source"+str(n)).encode()) for n in range(8)}
 policy={"schema_version":"1.0","enabled":True,"candidate_sha":candidate,"trusted_source_sha256":sources}
 scope={"policy":{"candidate_sha":candidate,"rollback_sha":install.ROLLBACK},
  "source_sha256":sources,"desired_state_before_sha256":legacy,
  "desired_state_after_sha256":h(current) if outcome=="accepted" else h(b"other"),
  "rollback_desired_state_sha256":h(current) if outcome=="rolled_back" else h(b"other")}
 adoption={"action":"ADOPT-EXACT-DAILY-AUDIT-JOURNAL","owner_oid":install.OID,
  "independently_verified_entra_owner":True,"policy_sha256":h(raw(policy)),"scope_sha256":h(raw(scope))}
 plan={**adoption,"scope":scope,"candidate_sha":candidate}
 private=Path("/var/lib/jason-audit-journal/private")
 records={
  Path("/etc/jason-owner-release/audit-journal-v1.json"):(raw(policy),0o600),
  private/"adoption.json":(raw(adoption),0o400),private/"release-plan.json":(raw(plan),0o400),
  private/"release-journal.json":(raw({"outcome":outcome,"scope_sha256":h(raw(scope))}),0o400)}
 for n in range(8):
  records[Path("/usr/local/lib/jason/audit-journal/trusted/tools/fixture_"+str(n)+".py")]=(
   ("source"+str(n)).encode(),0o444)
 def read(path,uid,mode):
  assert uid==0
  value,expected_mode=records[Path(path)]
  assert mode==expected_mode
  return value
 return current,legacy,{"read":read},records

def test_original_accepted_policy_needs_no_other_component():
 current=b"original policy"
 assert install.accepted_installation_policy({},current,h(current))["kind"]=="accepted_stage_e_policy"

@pytest.mark.parametrize("outcome",["accepted","rolled_back"])
def test_exact_completed_journal_policy_is_recognized(outcome):
 current,legacy,c,_=fixture(outcome)
 result=install.accepted_installation_policy(c,current,legacy)
 assert result["kind"]=="accepted_journal_policy" and result["outcome"]==outcome

@pytest.mark.parametrize("tamper",["policy_bytes","owner","acceptance","source","scope","foreign_receipt"])
def test_unapproved_policy_or_component_evidence_is_denied(tamper):
 current,legacy,c,records=fixture()
 private=Path("/var/lib/jason-audit-journal/private")
 if tamper=="policy_bytes":current=raw({"fixture":"unapproved root policy"})
 elif tamper=="owner":
  path=private/"adoption.json";value=json.loads(records[path][0]);value["owner_oid"]="unapproved"
  records[path]=(raw(value),0o400)
 elif tamper=="acceptance":records[private/"release-journal.json"]=(raw({"outcome":"running"}),0o400)
 elif tamper=="foreign_receipt":
  records[private/"release-journal.json"]=(raw({"outcome":"accepted","scope_sha256":"f"*64}),0o400)
 elif tamper=="source":
  path=Path("/usr/local/lib/jason/audit-journal/trusted/tools/fixture_0.py")
  records[path]=(b"changed source",0o444)
 else:
  path=private/"release-plan.json";value=json.loads(records[path][0])
  value["scope"]["desired_state_after_sha256"]=h(current+b"unapproved")
  records[path]=(raw(value),0o400)
 with pytest.raises(PermissionError):install.accepted_installation_policy(c,current,legacy)
