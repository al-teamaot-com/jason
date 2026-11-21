import copy
import pytest
from tools.audit_journal_container_release import planned_configuration,exact_original_configuration,readonly_binds
from tools.audit_journal_legacy_reconcile_worker import guarded_materializer

CANDIDATE="a"*40

def before(role="jason-runtime"):
 return {"Name":"/"+role,"Id":"b"*64,"Image":"sha256:"+"c"*64,
 "Config":{"User":"1000:1000","Env":["EXISTING=fixture-value"],"Labels":{"existing":"fixture"},
 "Cmd":["python","-m","fixture"],"Entrypoint":["fixture-entry"],"Healthcheck":{"Test":["CMD","fixture-health"]}},
 "HostConfig":{"Privileged":False,"AutoRemove":False,"ReadonlyRootfs":True,"CapDrop":["ALL"],
 "Mounts":[{"Type":"bind","Source":"/fixture/existing","Target":"/fixture/data","ReadOnly":True}],
 "PortBindings":{"8080/tcp":[{"HostIp":"127.0.0.1","HostPort":"18080"}]},
 "NetworkMode":"fixture-net","RestartPolicy":{"Name":"unless-stopped"}},
 "Mounts":[{"Type":"bind","Source":"/fixture/existing","Destination":"/fixture/data","RW":False}],
 "NetworkSettings":{"Networks":{"fixture-net":{"IPAMConfig":None,"Aliases":["jason-runtime","b"*12]}}}}

@pytest.mark.parametrize("role",["jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core"])
def test_component_plan_preserves_runtime_and_adds_only_declared_bindings(role):
 source=before(role);saved=copy.deepcopy(source)
 plan=planned_configuration(source,CANDIDATE)
 assert source==saved and plan["Image"]==source["Image"]
 assert all(plan[k]==source["Config"][k] for k in ("Cmd","Entrypoint","Healthcheck","User"))
 assert all(plan["HostConfig"][k]==source["HostConfig"][k] for k in
            ("ReadonlyRootfs","CapDrop","PortBindings","NetworkMode","RestartPolicy"))
 assert len(plan["HostConfig"]["Mounts"])==8
 assert plan["HostConfig"]["Mounts"][1:]==readonly_binds(role)
 assert "EXISTING=fixture-value" in plan["Env"]
 assert plan["Labels"]["existing"]=="fixture"

def test_conflicting_mount_is_denied_before_execution():
 source=before();bind=readonly_binds("jason-runtime")[0]
 source["Mounts"].append({"Type":"bind","Source":"/wrong","Destination":bind["Target"],"RW":False})
 with pytest.raises(PermissionError,match="MOUNT_CONFLICT"):planned_configuration(source,CANDIDATE)

def test_static_address_requires_a_deliberate_handoff():
 source=before();source["NetworkSettings"]["Networks"]["fixture-net"]["IPAMConfig"]={"IPv4Address":"192.0.2.10"}
 with pytest.raises(PermissionError,match="STATIC_NETWORK"):planned_configuration(source,CANDIDATE)

def test_original_spec_retains_existing_configuration():
 source=before();restored=exact_original_configuration(source)
 assert restored["Image"]==source["Image"] and restored["Env"]==source["Config"]["Env"]
 assert restored["HostConfig"]==source["HostConfig"]
 assert restored["Cmd"]==source["Config"]["Cmd"] and restored["Entrypoint"]==source["Config"]["Entrypoint"]

def test_compatibility_wrapper_only_adds_a_denial_and_preserves_arguments():
 calls=[]
 def original(*args,**kwargs):calls.append((args,kwargs));return "original-result"
 guard=guarded_materializer(original,lambda:set())
 with pytest.raises(PermissionError,match="COMPATIBLE_SCOPED_RELEASE"):guard("d"*40)
 assert calls==[]
 allowed=guarded_materializer(original,lambda:{"d"*40})
 assert allowed("d"*40,test=True)=="original-result"
 assert calls==[(("d"*40,),{"test":True})]
 legacy=guarded_materializer(original,lambda:None)
 assert legacy("e"*40)=="original-result"
