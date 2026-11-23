"""Exact journal recovery headroom without deleting rollback material."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from tools import audit_journal_install as install
from tools import audit_journal_release_scope as scope
from tools import production_drift_guard as drift
from tools.audit_journal_container_release import ROLES


def policy():
 return {"schema_version":"1.0","required_system_units":["existing-required.timer"],
  "allowed_system_units":["existing-allowed.service"],
  "rollback_container_prefixes":["jason-runtime-rollback-","jason-mcp-pilot-rollback-",
   "jason-mcp-rollback-","jason-teams-gateway-rollback-"],
  "max_stopped_rollback_containers":21,"unrelated":{"unchanged":True}}


def docker_names(monkeypatch,names):
 def command(argv,**kwargs):
  assert argv==["/usr/bin/docker","ps","-a","--filter","status=exited","--format","{{.Names}}"]
  return "\n".join(names)
 monkeypatch.setattr(install,"command",command)
 monkeypatch.setattr(drift,"run",lambda argv:"\n".join(names))


def test_exact_additive_policy_and_event_preserving_rollback():
 before=policy();saved=deepcopy(before);after=scope.desired_after(before)
 assert before==saved and after["max_stopped_rollback_containers"]==27
 assert scope.ROLLBACK_CONTAINER_RESERVE==2*len(ROLES)==6
 assert {k for k in before if before[k]!=after[k]}=={
  "required_system_units","allowed_system_units","rollback_container_prefixes","max_stopped_rollback_containers"}
 assert set(after["required_system_units"])==set(before["required_system_units"])|{
  "jason-audit-journal-data-recovery.service","jason-audit-journal-maintenance.timer"}
 assert set(after["allowed_system_units"])==set(before["allowed_system_units"])|{
  "jason-audit-journal-maintenance.service","jason-audit-journal-release.service"}
 assert after["rollback_container_prefixes"]==before["rollback_container_prefixes"]+[
  "jason-pmv4-ticket-core-rollback-audit-"]
 rollback=scope.desired_rollback(before)
 assert rollback["max_stopped_rollback_containers"]==27
 assert rollback["rollback_container_prefixes"]==after["rollback_container_prefixes"]
 assert "jason-audit-journal-maintenance.timer" not in rollback["required_system_units"]
 assert "jason-audit-journal-maintenance.timer" in rollback["allowed_system_units"]
 assert before==saved


@pytest.mark.parametrize("limit",[20,22,27,200,True,21.0,"21",None])
def test_unreviewed_before_limit_denied(limit):
 before=policy();before["max_stopped_rollback_containers"]=limit
 with pytest.raises(PermissionError,match="REVIEWED_ROLLBACK_BASELINE_REQUIRED"):
  scope.desired_after(before)


def test_missing_before_limit_denied():
 before=policy();del before["max_stopped_rollback_containers"]
 with pytest.raises(PermissionError,match="REVIEWED_ROLLBACK_BASELINE_REQUIRED"):
  scope.desired_after(before)


@pytest.mark.parametrize("count",[0,15,20,21])
def test_native_population_and_fixed_reserve(monkeypatch,count):
 names=["jason-runtime-rollback-historical-"+str(i) for i in range(count)]
 names += ["jason-pmv4-shadow-gateway","jason-mcp-signer-recovery-prior"]
 docker_names(monkeypatch,names)
 after,facts=install.recovery_capacity(scope,policy())
 assert facts["existing_names"]==drift.stopped_rollback_containers(after["rollback_container_prefixes"])
 assert facts["existing_count"]==count and facts["limit_before"]==21
 assert facts["limit_after"]==27 and facts["reserved_slots"]==6 and facts["cleanup_allowed"] is False
 assert after["max_stopped_rollback_containers"]==27


@pytest.mark.parametrize("count",[22,27,28])
def test_excess_existing_assets_denied_without_automatic_expansion(monkeypatch,count):
 docker_names(monkeypatch,["jason-runtime-rollback-old-"+str(i) for i in range(count)])
 with pytest.raises(PermissionError,match="STOPPED_CONTAINER_BASELINE_CAPACITY"):
  install.recovery_capacity(scope,policy())


def test_preexisting_ticket_recovery_counts_under_added_prefix(monkeypatch):
 docker_names(monkeypatch,["jason-runtime-rollback-old-"+str(i) for i in range(21)]+[
  "jason-pmv4-ticket-core-rollback-audit-before-"+"a"*12])
 with pytest.raises(PermissionError,match="STOPPED_CONTAINER_BASELINE_CAPACITY"):
  install.recovery_capacity(scope,policy())


@pytest.mark.parametrize("names",[["duplicate","duplicate"],["jason-runtime-rollback-ok","","other"] ,["bad name"],["/bad/path"]])
def test_ambiguous_inventory_denied(monkeypatch,names):
 docker_names(monkeypatch,names)
 with pytest.raises(PermissionError,match="STOPPED_CONTAINER_INVENTORY"):
  install.recovery_capacity(scope,policy())


def test_docker_failure_is_not_empty_inventory(monkeypatch):
 monkeypatch.setattr(install.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=1,stdout="",stderr="unavailable"))
 with pytest.raises(PermissionError,match="COMMAND_FAILED"):
  install.recovery_capacity(scope,policy())


def test_reserve_must_fit_final_policy(monkeypatch):
 original=scope.desired_after
 def insufficient(before):
  after=original(before);after["max_stopped_rollback_containers"]=26;return after
 monkeypatch.setattr(scope,"desired_after",insufficient)
 docker_names(monkeypatch,["jason-runtime-rollback-old-"+str(i) for i in range(21)])
 with pytest.raises(PermissionError,match="STOPPED_CONTAINER_RECOVERY_CAPACITY"):
  install.recovery_capacity(scope,policy())


def test_reviewed_owner_scope_discloses_fixed_policy_delta(tmp_path,monkeypatch):
 monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",tmp_path/"absent")
 facts={"dataset_identity":{"device":3,"inode":7},"producer_before":{},"producer_after":{},
  "desired_after_sha256":"f"*64,"archive_root_metadata":{}}
 reviewed=scope.reviewed_scope("a"*40,{}, {}, {},facts)
 assert reviewed["rollback_container_limit_before"]==21 and reviewed["rollback_container_limit_after"]==27
 assert reviewed["rollback_container_reserve"]==6
 assert reviewed["initial_container_replacements"]==reviewed["possible_recovery_container_replacements"]==3
 assert reviewed["existing_rollback_containers_preserved"] is True
 assert reviewed["rollback_container_cleanup_allowed"] is False
