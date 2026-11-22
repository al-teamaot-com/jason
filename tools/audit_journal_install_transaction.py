"""Durable, idempotent filesystem bootstrap; never an authority issuer.

The caller supplies only the exact Owner-reviewed bundle. The transaction
journal is in the separate Root-only approval record, outside rollback targets.
"""
from __future__ import annotations
from hashlib import sha256
import json,os,stat
from pathlib import Path
from uuid import uuid4

def need(value,code):
 if not value:raise PermissionError("JOURNAL_BOOTSTRAP_"+code)
def digest(raw):return sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sync(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def raw_file(path,mode=None):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,"rb") as stream:
  meta=os.fstat(stream.fileno())
  need(stat.S_ISREG(meta.st_mode) and meta.st_uid==meta.st_gid==0 and meta.st_nlink==1
       and (mode is None or stat.S_IMODE(meta.st_mode)==mode)
       and meta.st_size<=16000000,"ROOT_RECORD_FILE")
  return stream.read(16000001)
def remove_scoped_temp(path,expected):
 temp=path.with_name("."+path.name+".audit-"+expected[:16]+".new")
 if os.path.lexists(temp):
  raw_file(temp);temp.unlink();sync(temp.parent)
 return temp

def atomic(path,raw,mode):
 temp=remove_scoped_temp(path,digest(raw))
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 try:
  with os.fdopen(fd,"wb") as stream:
   os.fchown(stream.fileno(),0,0);os.fchmod(stream.fileno(),mode)
   stream.write(raw);stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path);sync(path.parent)
 finally:
  if temp.exists():temp.unlink()

class InstallTransaction:
 def __init__(self,path,scope_sha256,*,fault=lambda _:None):
  need(os.geteuid()==0,"ROOT_REQUIRED");self.path=Path(path);self.fault=fault
  parent=self.path.parent.lstat()
  need(not self.path.parent.is_symlink() and parent.st_uid==parent.st_gid==0
       and stat.S_IMODE(parent.st_mode)==0o700,"PRIVATE_RECORD_DIRECTORY")
  self.state=json.loads(raw_file(self.path,0o600)) if self.path.exists() else {
   "scope_sha256":scope_sha256,"entries":[],"outcome":"installing"}
  need(self.state["scope_sha256"]==scope_sha256,"EXACT_SCOPE_BINDING")
  self.persist()
 @property
 def queued(self):return self.state["outcome"]=="queued"
 @queued.setter
 def queued(self,value):
  need(value is True,"QUEUED_STATE_CANNOT_BE_REVOKED")
  self.state["outcome"]="queued";self.persist()
 def persist(self):
  atomic(self.path,canonical(self.state),0o600);self.fault("intent_saved")
 def record(self,kind,path,**fields):
  path=str(path)
  prior=[r for r in self.state["entries"] if r["kind"]==kind and r["path"]==path]
  if prior:
   item=prior[0];need(all(item.get(k)==v for k,v in fields.items()),"RECORDED_ACTION_CHANGED")
   return item
  item={"kind":kind,"path":path,**fields};self.state["entries"].append(item);self.persist();return item
 def metadata(self,path,uid,gid,mode):
  path=Path(path)
  prior=[r for r in self.state["entries"] if r["kind"]=="metadata" and r["path"]==str(path)]
  if prior:item=prior[0]
  else:
   meta=path.lstat()
   need(not path.is_symlink() and stat.S_ISDIR(meta.st_mode),"METADATA_DIRECTORY")
   item=self.record("metadata",path,before=[meta.st_uid,meta.st_gid,stat.S_IMODE(meta.st_mode)],
                    after=[uid,gid,mode],identity=[meta.st_dev,meta.st_ino])
  need(item["after"]==[uid,gid,mode],"METADATA_ACTION_CHANGED")
  meta=path.lstat()
  need([meta.st_dev,meta.st_ino]==item["identity"] and
       [meta.st_uid,meta.st_gid,stat.S_IMODE(meta.st_mode)] in
       (item["before"],item["after"],[*item["after"][:2],item["before"][2]],
        [*item["before"][:2],item["after"][2]]),"METADATA_CHANGED")
  os.chown(path,uid,gid);path.chmod(mode);sync(path.parent);self.fault("metadata_applied")
 def directory(self,path,mode=0o755,uid=0,gid=0):
  path=Path(path)
  if os.path.lexists(path):
   meta=path.lstat()
   prior=any(r["kind"]=="directory" and r["path"]==str(path) and
             r["uid"]==uid and r["gid"]==gid and r["mode"]==mode for r in self.state["entries"])
   need(not path.is_symlink() and stat.S_ISDIR(meta.st_mode),"DIRECTORY_CUSTODY:"+path.name)
   if prior:
    need(meta.st_uid in (0,uid) and meta.st_gid in (0,gid) and not meta.st_mode&0o022,
         "INTERRUPTED_DIRECTORY_CUSTODY")
    os.chown(path,uid,gid);path.chmod(mode)
   need(meta.st_uid==uid and meta.st_gid==gid and stat.S_IMODE(meta.st_mode)==mode or prior,
        "DIRECTORY_CUSTODY:"+path.name)
   return
  if not path.parent.exists():self.directory(path.parent)
  self.record("directory",path,uid=uid,gid=gid,mode=mode)
  path.mkdir(mode=mode);os.chown(path,uid,gid);path.chmod(mode);sync(path.parent)
  self.fault("directory_created")
 def write(self,path,raw,mode=0o444):
  path=Path(path);expected=digest(raw)
  item=self.record("file",path,sha256=expected,mode=mode)
  if os.path.lexists(path):
   need(digest(raw_file(path,mode))==expected,"NEW_FILE_CHANGED:"+path.name);return
  atomic(path,raw,mode);self.fault("file_published")
 def replace(self,path,raw):
  path=Path(path);expected=digest(raw)
  prior=[r for r in self.state["entries"] if r["kind"]=="replace" and r["path"]==str(path)]
  item=prior[0] if prior else self.record("replace",path,before_hex=raw_file(path,0o600).hex(),
                                         after_sha256=expected)
  need(item["after_sha256"]==expected,"REPLACEMENT_SOURCE_CHANGED")
  current=raw_file(path,0o600)
  need(digest(current) in (digest(bytes.fromhex(item["before_hex"])),expected),"MODIFIED_TARGET_CHANGED")
  if digest(current)!=expected:atomic(path,raw,0o600)
  self.fault("replacement_published")
 def rollback(self):
  need(not self.queued,"QUEUED_WORKER_REQUIRES_GOVERNED_RECOVERY")
  self.state["outcome"]="rolling_back";self.persist()
  for item in reversed(self.state["entries"]):
   path=Path(item["path"]);kind=item["kind"]
   if kind=="replace":
    current=raw_file(path,0o600);old=bytes.fromhex(item["before_hex"])
    need(digest(current) in (digest(old),item["after_sha256"]),"ROLLBACK_TARGET_CHANGED")
    atomic(path,old,0o600)
   elif kind=="file":
    if path.parent.exists():remove_scoped_temp(path,item["sha256"])
    if os.path.lexists(path):
     need(digest(raw_file(path,item["mode"]))==item["sha256"],"ROLLBACK_NEW_FILE_CHANGED")
     path.unlink();sync(path.parent)
   elif kind=="directory" and path.exists():path.rmdir();sync(path.parent)
   elif kind=="metadata":
    m=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode)
         and [m.st_dev,m.st_ino]==item["identity"]
         and [m.st_uid,m.st_gid,stat.S_IMODE(m.st_mode)] in
         (item["before"],item["after"],[*item["after"][:2],item["before"][2]],
          [*item["before"][:2],item["after"][2]]),"ROLLBACK_DIRECTORY_CHANGED")
    uid,gid,mode=item["before"];os.chown(path,uid,gid);path.chmod(mode);sync(path.parent)
  self.state["outcome"]="rolled_back";self.persist()
