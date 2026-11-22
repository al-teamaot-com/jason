#!/usr/bin/env python3
"""Read-only privileged inventory; no service/data/configuration mutation."""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json,os,sqlite3,stat,subprocess,sys,time
from pathlib import Path

ACTIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
FILES=(
 "/etc/jason/release-readback-recovery/production-desired-state.json",
 "/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json",
 "/usr/local/lib/jason/release_host_reconcile_worker.py",
 "/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_live_audit_full_snapshot.py",
 "/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_operational_health.py",
 "/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_fast_health.py",
 "/usr/local/lib/jason/owner_signer_recovery.py",
)
NAMES=("jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core","jason-pmv4-shadow-gateway",
       "jason-teams-gateway")

def file_identity(path,*,digest=False):
 path=Path(path);m=path.lstat()
 if path.is_symlink() or not stat.S_ISREG(m.st_mode):raise ValueError("ROOT_INVENTORY_REGULAR_FILE_REQUIRED")
 out={"path":str(path),"uid":m.st_uid,"gid":m.st_gid,"mode":oct(stat.S_IMODE(m.st_mode)),
      "links":m.st_nlink,"bytes":m.st_size,"device":m.st_dev,"inode":m.st_ino}
 if digest:
  if m.st_size>2000000:raise ValueError("ROOT_INVENTORY_SOURCE_SIZE")
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,"rb") as stream:out["sha256"]=sha256(stream.read()).hexdigest()
 return out

def handles(path):
 key=path.stat();found=[];denied=[]
 for proc in Path("/proc").iterdir():
  if not proc.name.isdigit():continue
  try:items=list((proc/"fd").iterdir())
  except (FileNotFoundError,ProcessLookupError):continue
  except PermissionError:denied.append(int(proc.name));continue
  matched=False
  for item in items:
   try:m=item.stat()
   except (FileNotFoundError,ProcessLookupError):continue
   except PermissionError:denied.append(int(proc.name));continue
   if (m.st_dev,m.st_ino)==(key.st_dev,key.st_ino):matched=True
  if matched:
   try:comm=(proc/"comm").read_text().strip();uid=proc.stat().st_uid
   except (FileNotFoundError,ProcessLookupError):continue
   found.append({"pid":int(proc.name),"uid":uid,"comm":comm})
 return {"complete":not denied,"permission_denied_pids":sorted(set(denied)),"open_handles":found}

def container(name):
 result=subprocess.run(["/usr/bin/docker","inspect","--type=container",name],
                       capture_output=True,text=True,timeout=15,check=False)
 if result.returncode:return {"name":name,"present":False}
 row=json.loads(result.stdout)[0]
 # Never serialize Config.Env, command lines or secret values.
 return {"name":name,"present":True,"id":row["Id"],"image":row["Image"],
         "user":row["Config"]["User"],"running":row["State"]["Running"],
         "health":row["State"].get("Health",{}).get("Status"),
         "mounts":[{k:item.get(k) for k in ("Type","Source","Destination","RW")}
                   for item in row["Mounts"]]}

def ledger(path):
 # Privileged inventory reads filesystem metadata only. SQLite queries, if
 # needed, stay with the ordinary writer identity in a separate readback.
 if not path.exists():return {"path":str(path),"present":False}
 return {"present":True,**file_identity(path)}


def main():
 if os.geteuid()!=0 or sys.flags.isolated!=1:raise PermissionError("READ_ONLY_ISOLATED_ROOT_REQUIRED")
 start=time.monotonic()
 report={"schema_version":"1.0","action":"READ-ONLY-AUDIT-JOURNAL-RELEASE-INVENTORY",
         "observed_at":datetime.now(timezone.utc).isoformat(),"production_mutations":False,
         "services_restarted":False,"owner_approval_issued":False,"audit_payloads_exported":False}
 report["active"]=file_identity(ACTIVE)
 report["process_inventory"]=handles(ACTIVE)
 report["protected_files"]=[file_identity(Path(name),digest=True) for name in FILES]
 report["archive_drive"]={"path":str(ARCHIVE),"device":ARCHIVE.stat().st_dev,
     "separate_filesystem":ARCHIVE.stat().st_dev!=ACTIVE.parent.stat().st_dev,
     "free_bytes":os.statvfs(ARCHIVE).f_bavail*os.statvfs(ARCHIVE).f_frsize}
 report["local_free_bytes"]=os.statvfs(ACTIVE.parent).f_bavail*os.statvfs(ACTIVE.parent).f_frsize
 report["containers"]=[container(name) for name in NAMES]
 report["known_ledgers"]=[ledger(Path(name)) for name in (
     "/var/lib/jason/openclaw/governed-execution.sqlite3",
     "/var/lib/jason/governed-ticket-shared/governed-execution.sqlite3")]
 report["owner_objective_installed"]=Path("/usr/local/lib/jason/owner-objective").is_dir()
 report["elapsed_seconds"]=round(time.monotonic()-start,3)
 report["status"]="read_only_root_inventory_complete" if report["process_inventory"]["complete"] else "root_inventory_incomplete"
 print(json.dumps(report,indent=2,sort_keys=True))
 return 0 if report["process_inventory"]["complete"] else 2

if __name__=="__main__":
 try:raise SystemExit(main())
 except (OSError,ValueError,sqlite3.Error) as exc:
  raise SystemExit("DENIED:ROOT_INVENTORY:"+type(exc).__name__)
