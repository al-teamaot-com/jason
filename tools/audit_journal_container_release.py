"""Exact container configuration changes for the adopted journal component.

Pure planning preserves existing command, secrets, ports, networks and security.
Production mutation is called only by the separately verified Root release
transaction. No credentials or complete container configurations are logged.
"""
from __future__ import annotations
import copy,hashlib,http.client,json,os,re,socket
from pathlib import Path
from urllib.parse import quote

ROLES={"jason-runtime":"/app/implementation/orchestrator",
       "jason-mcp-pilot":"/opt/jason-src/implementation/orchestrator",
       "jason-pmv4-ticket-core":"/app/implementation/orchestrator"}
FILES=("event_store.py","segmented_journal.py","journal_outcomes.py")
PROFILE="/run/jason/audit-journal/profile.json"
TRUST="/usr/local/lib/jason/audit-journal/trusted/implementation/orchestrator"
DATA=("/run/jason/audit-journal","/var/lib/jason-audit-journal/control",
      "/var/lib/jason-audit-journal/pending","/srv/jason/archive/governed-audit/orchestration")

def need(value,code):
 if not value:raise PermissionError("AUDIT_RELEASE_"+code)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def readonly_binds(role):
 need(role in ROLES,"CONSUMER_ROLE")
 return [*(dict(Type="bind",Source=TRUST+"/"+name,Target=ROLES[role]+"/"+name,ReadOnly=True)
             for name in FILES),
         *(dict(Type="bind",Source=path,Target=path,ReadOnly=True) for path in DATA)]

def planned_configuration(before,candidate):
 role=before["Name"].removeprefix("/")
 need(role in ROLES and re.fullmatch("[0-9a-f]{40}",candidate),"EXACT_CANDIDATE_AND_ROLE")
 need(before["Config"].get("User")=="1000:1000","CONSUMER_UID")
 need(before["HostConfig"].get("Privileged") is False,"PRIVILEGED_CONSUMER_DENIED")
 need(not before["HostConfig"].get("AutoRemove"),"AUTOREMOVE_CONSUMER_DENIED")
 config=copy.deepcopy(before["Config"]);host=copy.deepcopy(before["HostConfig"])
 config["Image"]=before["Image"]  # exact SAME already-running image
 entries=config.get("Env") or []
 need(len({v.split("=",1)[0] for v in entries})==len(entries),"DUPLICATE_EXISTING_ENVIRONMENT")
 env={v.split("=",1)[0]:v.split("=",1)[1] for v in entries}
 selected=env.get("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE","")
 need(selected in ("",PROFILE),"EXISTING_PROFILE_CONFLICT")
 env["JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE"]=PROFILE
 config["Env"]=[key+"="+value for key,value in env.items()]
 labels=config.setdefault("Labels",{})
 need(labels.get("com.teamaot.jason.audit-journal-source") in (None,candidate),"OTHER_JOURNAL_RELEASE")
 labels["com.teamaot.jason.audit-journal-source"]=candidate
 mounts=list(host.get("Mounts") or [])
 by_target={row["Destination"]:row for row in before.get("Mounts",[])}
 for bind in readonly_binds(role):
  existing=by_target.get(bind["Target"])
  if existing:
   need(existing.get("Type")=="bind" and existing.get("Source")==bind["Source"]
        and existing.get("RW") is False,"EXISTING_COMPONENT_MOUNT_CONFLICT")
  else:mounts.append(bind)
 host["Mounts"]=mounts
 networks={}
 for name,endpoint in before["NetworkSettings"]["Networks"].items():
  ipam=endpoint.get("IPAMConfig")
  need(not ipam or not any(ipam.get(k) for k in ("IPv4Address","IPv6Address")),
       "STATIC_NETWORK_REQUIRES_EXACT_HANDOFF")
  aliases=[v for v in endpoint.get("Aliases") or [] if v not in (before["Id"],before["Id"][:12])]
  networks[name]={"Aliases":aliases}
  if endpoint.get("DriverOpts"):networks[name]["DriverOpts"]=copy.deepcopy(endpoint["DriverOpts"])
 return {**config,"HostConfig":host,"NetworkingConfig":{"EndpointsConfig":networks}}

def exact_original_configuration(before):
 # Used only after the archive-backed legacy database is published, or before
 # initial data cutover. Never restore legacy readers onto segmented-only data.
 role=before["Name"].removeprefix("/");need(role in ROLES,"ORIGINAL_CONSUMER_ROLE")
 config=copy.deepcopy(before["Config"]);config["Image"]=before["Image"]
 networks={name:{"Aliases":[v for v in item.get("Aliases") or []
             if v not in (before["Id"],before["Id"][:12])]}
           for name,item in before["NetworkSettings"]["Networks"].items()}
 return {**config,"HostConfig":copy.deepcopy(before["HostConfig"]),
         "NetworkingConfig":{"EndpointsConfig":networks}}

class UnixHTTP(http.client.HTTPConnection):
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
  self.sock.settimeout(self.timeout);self.sock.connect("/var/run/docker.sock")

class DockerEngine:
 def __init__(self):
  version=self.call("GET","/version",versioned=False)
  need(re.fullmatch(r"1\.[0-9]+",version.get("ApiVersion","")),"ENGINE_VERSION")
  self.version=version["ApiVersion"]
 def call(self,method,path,body=None,*,versioned=True,timeout=120):
  connection=UnixHTTP("localhost",timeout=timeout)
  try:
   encoded=None if body is None else json.dumps(body,separators=(",",":")).encode()
   url=("/v"+self.version if versioned else "")+path
   connection.request(method,url,body=encoded,headers={"Content-Type":"application/json"})
   response=connection.getresponse();raw=response.read(8000001)
   need(len(raw)<=8000000,"ENGINE_RESPONSE_BOUND")
   need(200<=response.status<300,"ENGINE_HTTP_"+str(response.status))
   return json.loads(raw) if raw else {}
  finally:connection.close()
 def inspect(self,role):
  need(role in ROLES,"INSPECT_ROLE");return self.lookup(role,required=True)
 def lookup(self,reference,required=False):
  allowed=reference in ROLES or re.fullmatch("[0-9a-f]{64}",reference) or any(
      re.fullmatch(role+r"-rollback-audit-(before|failed)-[0-9a-f]{12}",reference) for role in ROLES)
  need(allowed,"EXACT_CONTAINER_REFERENCE")
  try:return self.call("GET","/containers/"+quote(reference,safe="")+"/json")
  except PermissionError as exc:
   if not required and str(exc)=="AUDIT_RELEASE_ENGINE_HTTP_404":return None
   raise
 def replace(self,role,body,*,expected_id,backup_name):
  need(os.geteuid()==0,"ROOT_RELEASE_EXECUTOR_REQUIRED")
  need(role in ROLES and re.fullmatch(role+r"-rollback-audit-(before|failed)-[0-9a-f]{12}",backup_name),
       "REPLACEMENT_ROLE")
  current=self.lookup(role);backup=self.lookup(backup_name)
  if current is not None and current["Id"]==expected_id:
   need(current["Image"]==body["Image"] and backup is None,"LIVE_CONSUMER_CHANGED")
   if current["State"]["Running"]:self.call("POST","/containers/"+expected_id+"/stop?t=30")
   # An interrupted stop/rename is resumed only against the recorded exact ID.
   self.call("POST","/containers/"+expected_id+"/rename?name="+quote(backup_name,safe=""))
   current=None;backup=self.lookup(backup_name,required=True)
  need(backup is not None and backup["Id"]==expected_id and not backup["State"]["Running"],
       "EXACT_STOPPED_BEFORE_IMAGE_REQUIRED")
  if current is None:
   result=self.call("POST","/containers/create?name="+quote(role,safe=""),body)
   need(re.fullmatch("[0-9a-f]{64}",result.get("Id","")),"CREATED_CONTAINER_ID")
   current=self.lookup(role,required=True)
   need(current["Id"]==result["Id"],"CREATED_CONTAINER_CHANGED")
  # A lost create/start response never causes another replacement.
  need(configuration_matches(current,body),"UNKNOWN_REPLACEMENT_CONFIGURATION")
  if not current["State"]["Running"]:self.call("POST","/containers/"+current["Id"]+"/start")
  return {"role":role,"before_id":expected_id,"after_id":current["Id"],"image_id":body["Image"]}


def configuration_matches(current,body):
 if current["Image"]!=body["Image"]:return False
 if any(current["Config"].get(k)!=v for k,v in body.items()
        if k not in ("Image","HostConfig","NetworkingConfig")):return False
 # Docker normalizes mount syntax. Validate destinations and read/write modes
 # independently; every remaining HostConfig setting must be preserved.
 if any(current["HostConfig"].get(k)!=v for k,v in body["HostConfig"].items() if k!="Mounts"):return False
 actual={r["Destination"]:(r["Type"],r["Source"],r["RW"]) for r in current["Mounts"]}
 return all(actual.get(r["Target"])==(r["Type"],r["Source"],not r.get("ReadOnly",False))
            for r in body["HostConfig"].get("Mounts") or [])
