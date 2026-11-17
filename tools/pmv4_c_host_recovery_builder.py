#!/usr/bin/env python3
"""Build exact source-only Stage C canonical host recovery packet; never deploy."""
from __future__ import annotations
import hashlib,json,os,stat,subprocess,shutil,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
ARCHIVE=Path("/srv/jason/archive/engineering-artifacts")
PREVIOUS="13917410bb0ea1d5d37a314b3a3f131d416bf154"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION="pmv4-c-one-owner-exact-canonical-host-recovery-v1"
EXPORTERS=(
 "jason-usage-exporter.service","jason-usage-attribution-exporter.service",
 "jason-security-control-exporter.service","jason-reflection-exporter.service",
 "jason-resolution-memory-exporter.service",
)
HEALTH=("jason-openclaw-authority-health.service",
        "jason-openclaw-authority-full-integrity.service")
EXISTING_DROPINS=(
 "/etc/systemd/system/jason-openclaw-authority-health.service.d/91-owner-emergency-full-proof-degraded.conf",
 "/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/91-owner-full-proof-v2.conf",
 "/etc/systemd/system/jason-security-control-exporter.service.d/10-owner-approved-bounded-projection.conf",
)
SOURCES=("tools/pmv4_c_host_recovery_root.py",
         "tools/pmv4_c_host_recovery_owner.py",
         "tools/pmv4_c_authority_health_adapter.py",
         "tools/pmv4_c_host_consumer_projection.py")
def need(ok,reason):
 if not ok:raise RuntimeError(reason)
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def call(args):
 x=subprocess.run(args,capture_output=True,text=True,timeout=30)
 need(x.returncode==0,"HOST_BUILDER_DEPENDENCY:"+args[-1]);return x.stdout.strip()
def trusted_root_file(p):
 s=p.lstat()
 need(not p.is_symlink() and stat.S_ISREG(s.st_mode) and
      s.st_uid==0 and s.st_nlink==1 and not s.st_mode&0o022,
      "HOST_BUILDER_ROOT_FILE_NOT_TRUSTED:"+p.name)
 return digest(p.read_bytes())
def drops():
 from tools.pmv4_c_host_consumer_projection import all_dropins
 exact=all_dropins()
 executable="/usr/local/lib/jason/pmv4-c-canonical-health-v1/pmv4_c_authority_health_adapter.py"
 for unit,kind in ((HEALTH[0],"fast"),(HEALTH[1],"full")):
  # The LKG full checker opens SQLite's active WAL family read/write for
  # journal locks while doing integrity/backup checks. The old systemd sandbox
  # allowed the legacy state root; Stage C moved that same inode to SHARED.
  # Only the full proof service (never the fast checker) gets exact canonical
  # directory RW; no provider roles or external network are introduced.
  extra=("ReadWritePaths=/var/lib/jason/governed-ticket-shared\n"
         "TimeoutStartSec=5700\nNice=19\nIOSchedulingClass=idle\n") if kind=="full" else ""
  exact[unit]=("[Service]\nExecStart=\nExecStart=/usr/bin/python3 "+executable+
               " --mode "+kind+"\nReadOnlyPaths=/var/lib/jason/governed-ticket-shared/"
               "orchestration-events.sqlite3\n"+extra).encode()
 need(set(exact)==set(HEALTH)|set(EXPORTERS),"HOST_BUILDER_DROPINS_FOREIGN")
 return exact
def build():
 sha=call(["/usr/bin/git","-C",str(BASE),"rev-parse","HEAD"])
 need(call(["/usr/bin/gh","api","repos/al-teamaot-com/jason/branches/main",
            "--jq",".commit.sha"])==sha,"HOST_BUILDER_SOURCE_NOT_MAIN")
 need(not call(["/usr/bin/git","-C",str(BASE),"status","--porcelain"]),
      "HOST_BUILDER_SOURCE_DIRTY")
 need(Path("/opt/jason/current").resolve().name==LKG,"HOST_BUILDER_LKG_CHANGED")
 from tools.pmv4_c_authority_health_adapter import canonical_path_gate
 canonical_path_gate()
 prior=ARCHIVE/("pmv4-c-"+PREVIOUS)
 old=json.loads((prior/"root-release-plan.json").read_bytes())
 need(old["candidate_sha"]==PREVIOUS,"HOST_BUILDER_PRIOR_PLAN_FOREIGN")
 proof=prior/"root-oneowner-proof.json"
 need(proof.is_file(),"HOST_BUILDER_PREVIOUS_PROOF_MISSING")
 db={}
 for original,meta in old["db_identities"].items():
  name=Path(original).name
  ticket=name in ("autonomy-operational-work.sqlite3",
                  "playbook-autonomy.sqlite3","autonomy-targeted-wakes.sqlite3",
                  "ticket-split.sqlite3")
  p=Path("/var/lib/jason/ticket-core" if ticket else
         "/var/lib/jason/governed-ticket-shared")/name
  s=p.lstat()
  need((s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_nlink)==
       (meta["device"],meta["inode"],1000,1000,0o600,1) and
       not Path(original).exists() and not Path(original).is_symlink(),
       "HOST_BUILDER_MIGRATED_INODE_CHANGED:"+name)
  db[str(p)]={"device":s.st_dev,"inode":s.st_ino,"uid":1000,"gid":1000,"mode":384}
 roots={}
 from tools.pmv4_c_host_consumer_projection import verify_fragment_bytes
 for n in (*HEALTH,*EXPORTERS):
  installed=Path("/etc/systemd/system")/n
  if n in EXPORTERS:
   source=BASE/"infrastructure/showcase/systemd"/n
   need(verify_fragment_bytes(source,installed,require_root=True)==
        trusted_root_file(installed),
        "HOST_BUILDER_EXPORTER_SOURCE_NOT_REVIEWED:"+n)
  else:
   source=(Path("/opt/jason/current") if n==HEALTH[1]
           else BASE)/"infrastructure/openclaw-operations/systemd"/n
   need(source.read_bytes()==installed.read_bytes(),
        "HOST_BUILDER_HEALTH_UNIT_SOURCE_NOT_REVIEWED:"+n)
   if n==HEALTH[1]:
    # The root-authorized LKG still has the 3900s legacy unit fragment,
    # with a separately owner-approved 5700s v2 override. A new repository
    # 5700s source fragment is NOT authority to replace the installed LKG.
    need(digest(installed.read_bytes())==
         "9c9b45d50c22243c8fdac75c09f1208076e1d74c719a645405035b6454262a14",
         "HOST_BUILDER_PRIOR_APPROVED_FULL_UNIT_CHANGED")
  roots[str(installed)]=trusted_root_file(installed)
 for raw in EXISTING_DROPINS:roots[raw]=trusted_root_file(Path(raw))
 files={name:digest((BASE/name).read_bytes()) for name in SOURCES}
 for n,p in (("native_signer","/usr/local/lib/jason/owner_signed_release.py"),
             ("native_oauth","/usr/local/lib/jason/owner_signer_recovery.py")):
  files[n]=trusted_root_file(Path(p))
 need(files["native_signer"]=="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3" and
      files["native_oauth"]=="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153",
      "HOST_BUILDER_NATIVE_SIGNER_MISMATCH")
 containers={}
 for n in ("jason-runtime","jason-mcp-pilot"):
  item=json.loads(call(["/usr/bin/docker","inspect",n]))[0]
  need(item["State"]["Running"] is True,"HOST_BUILDER_CONTAINER_STOPPED")
  containers[n]={"id":item["Id"],"image":item["Image"]}
 dropins=drops()
 plan={
  "schema_version":"1.0","action":ACTION,"candidate_sha":sha,
  "rollback_sha":LKG,"production_lkg_sha":LKG,
  "previous_stage_c_sha":PREVIOUS,
  "previous_stage_c_plan_sha256":digest((prior/"root-release-plan.json").read_bytes()),
  "previous_stage_c_proof_sha256":digest(proof.read_bytes()),
  "previous_stage_c_approval_id":"owner-mcp-2d58eede2bac4c9a82fb0328a15dfaa2",
  "owner_consents":1,"standing_authority":False,"later_stages_authorized":False,
  "no_database_relocation":True,"no_provider_mutation":True,
  "breaker_revalidation_native_only":True,
  "requires_genuine_canonical_full_proof":True,
  "service_restarts":list(EXPORTERS),
  "freeze_sha256":digest(Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze").read_bytes()),
  "hold_sha256":digest(Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold").read_bytes()),
  "db_identities":db,"existing_container_identities":containers,
  "root_baseline_hashes":roots,
  "dropin_hashes":{k:digest(v) for k,v in dropins.items()},
  "source_hashes":files,
 }
 plan["scope_sha256"]=digest(canon(plan))
 target=ARCHIVE/("pmv4-c-host-recovery-"+sha)
 stage=ARCHIVE/(".pmv4-c-host-recovery-"+sha+".building")
 need(not target.exists() and not stage.exists(),"HOST_BUILDER_PACKET_EXISTS")
 stage.mkdir(mode=0o700)
 try:
  for rel in SOURCES:
   dest=stage/("tools/"+Path(rel).name if rel.endswith(("_root.py","_owner.py")) else "src/"+rel)
   dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes((BASE/rel).read_bytes());dest.chmod(0o400)
  for unit,raw in dropins.items():
   dest=stage/"dropins"/(unit+".conf");dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(raw);dest.chmod(0o400)
  (stage/"root-release-plan.json").write_bytes(canon(plan))
  (stage/"root-release-plan.json").chmod(0o400)
  launcher="""#!/usr/bin/env bash
set -euo pipefail
A='"""+str(target)+"""'
mode="$1"
case "$mode" in
 --check-only)
   python3 -B "$A/tools/pmv4_c_host_recovery_owner.py" --plan "$A/root-release-plan.json" --check-only ;;
 --execute)
   python3 -B "$A/tools/pmv4_c_host_recovery_owner.py" --plan "$A/root-release-plan.json" --check-only
   sudo -k /usr/bin/python3 -B "$A/tools/pmv4_c_host_recovery_root.py" --plan "$A/root-release-plan.json" --preflight
   python3 -B "$A/tools/pmv4_c_host_recovery_owner.py" --plan "$A/root-release-plan.json" --authorize
   sudo -n /usr/bin/python3 -B "$A/tools/pmv4_c_host_recovery_root.py" --plan "$A/root-release-plan.json" --execute ;;
 *) echo 'HOST_RECOVERY_MODE_DENIED'; exit 2 ;;
esac
"""
  l=stage/"tools"/"pmv4_c_host_recovery_local.sh";l.write_text(launcher);l.chmod(0o500)
  os.rename(stage,target)
 except BaseException:
  if stage.exists():shutil.rmtree(stage)
  raise
 print("HOST_RECOVERY_IMMUTABLE_PACKET_BUILT=PASS")
 print("EXACT_SOURCE_SHA="+sha)
 print("EXACT_SCOPE_SHA256="+plan["scope_sha256"])
 print("PRODUCTION_MUTATIONS=false; OWNER_APPROVAL=false")
if __name__=="__main__":
 try:build()
 except BaseException as e:
  print("HOST_RECOVERY_BUILDER_DENIED",type(e).__name__,str(e),file=sys.stderr)
  raise SystemExit(2)
