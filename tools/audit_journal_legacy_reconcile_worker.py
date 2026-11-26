#!/usr/bin/env python3
"""Add a data-compatibility denial to the unchanged installed Root worker.

All original validation, exact approvals and request processing remain in the
pinned worker. Only whole-host script materialization receives the additional
adopted-data check. Independent typed actions keep their original path.
"""
from __future__ import annotations
import hashlib,importlib.util,os,re,runpy,stat,sys
from pathlib import Path

ENTRY=Path("/usr/local/lib/jason/audit-journal/trusted/tools/audit_journal_legacy_reconcile_worker.py")
WORKER=Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
WORKER_SHA="dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896"
ADOPTION=Path("/var/lib/jason-audit-journal/private/adoption.json")

def guarded_materializer(original,compatibility):
 def materialize(revision,*args,**kwargs):
  allowed=compatibility()
  if allowed is not None and revision not in allowed:
   raise PermissionError("AUDIT_DATA_REQUIRES_COMPATIBLE_SCOPED_RELEASE")
  return original(revision,*args,**kwargs)
 return materialize

def adopted_compatibility():
 if not ADOPTION.exists():return None
 # This validates the Root-only independently issued adoption, exact policy,
 # source closure, persistent profile and protected storage ancestry.
 source=ENTRY.with_name("audit_journal_control.py")
 namespace=runpy.run_path(str(source),run_name="audit_data_admission")
 controller=namespace["root_controller"]()
 policy=namespace["read_control"](namespace["POLICY"],0,0o600)
 values=policy.get("compatible_host_releases",[])
 if not isinstance(values,list) or any(not isinstance(v,str) or re.fullmatch("[0-9a-f]{40}",v) is None for v in values):
  raise PermissionError("AUDIT_DATA_COMPATIBLE_RELEASE_POLICY_INVALID")
 return set(values)

def main():
 if os.geteuid()!=0 or sys.flags.isolated!=1 or Path(__file__).resolve()!=ENTRY:
  raise PermissionError("AUDIT_DATA_INSTALLED_ISOLATED_ROOT_REQUIRED")
 meta=WORKER.lstat()
 if (WORKER.is_symlink() or not stat.S_ISREG(meta.st_mode) or meta.st_uid!=0 or meta.st_gid!=0
     or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o755
     or hashlib.sha256(WORKER.read_bytes()).hexdigest()!=WORKER_SHA):
  raise PermissionError("AUDIT_DATA_ORIGINAL_ROOT_WORKER_CHANGED")
 sys.path[:0]=[str(ENTRY.parent.parent),str(ENTRY.parent.parent/"implementation")]
 spec=importlib.util.spec_from_file_location("audit_original_root_worker",WORKER)
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 module._candidate_reconcile_script=guarded_materializer(module._candidate_reconcile_script,adopted_compatibility)
 module.main()

if __name__=="__main__":main()
