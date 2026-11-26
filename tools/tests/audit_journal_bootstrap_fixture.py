"""Root filesystem interruption tests inside the no-Host-mount test image."""
import os,runpy,stat
from pathlib import Path

def exercise(base,trust):
 helpers=runpy.run_path(str(trust/"tools/audit_journal_install_transaction.py"))
 Tx=helpers["InstallTransaction"];hash_bytes=helpers["digest"]
 cases=0
 for point in ("intent_saved","metadata_applied","directory_created","file_published","replacement_published"):
  root=base/("bootstrap-"+point);root.mkdir(mode=0o755)
  record=root/"record";record.mkdir(mode=0o700)
  top=root/"archive";top.mkdir();os.chown(top,1000,984);top.chmod(0o2770)
  old=root/"desired.json";old.write_bytes(b"original");old.chmod(0o600)
  target=root/"new";file=target/"source.py"
  tx=Tx(record/"transaction.json","a"*64)
  fired=[]
  def fault(at):
   if at==point and not fired:fired.append(at);raise SystemExit("power-loss")
  tx.fault=fault
  def apply(t):
   t.metadata(top,0,0,0o755);t.directory(target);t.write(file,b"reviewed-source")
   t.replace(old,b"reviewed-desired")
  try:apply(tx)
  except SystemExit:pass
  else:raise AssertionError("injection missed")
  resumed=Tx(record/"transaction.json","a"*64);apply(resumed)
  assert file.read_bytes()==b"reviewed-source" and old.read_bytes()==b"reviewed-desired"
  assert top.stat().st_uid==0 and stat.S_IMODE(top.stat().st_mode)==0o755
  try:Tx(record/"transaction.json","b"*64)
  except PermissionError:pass
  else:raise AssertionError("scope substitution accepted")
  resumed.rollback()
  assert not target.exists() and old.read_bytes()==b"original"
  assert (top.stat().st_uid,top.stat().st_gid,stat.S_IMODE(top.stat().st_mode))==(1000,984,0o2770)
  cases+=1
 # A temporary file interrupted before rename is recovered using only the
 # deterministic name bound to this exact Root transaction and content hash.
 root=base/"bootstrap-partial";root.mkdir();private=root/"record";private.mkdir(mode=0o700)
 tx=Tx(private/"transaction.json","c"*64);target=root/"payload"
 value=b"exact-payload";expected=hash_bytes(value)
 tx.record("file",target,sha256=expected,mode=0o444)
 partial=root/("."+target.name+".audit-"+expected[:16]+".new");partial.write_bytes(b"partial")
 resumed=Tx(private/"transaction.json","c"*64);resumed.write(target,value)
 assert target.read_bytes()==value and not partial.exists()
 resumed.queued=True
 try:resumed.rollback()
 except PermissionError:pass
 else:raise AssertionError("queued worker was undone blindly")
 assert target.read_bytes()==value
 return cases+1
