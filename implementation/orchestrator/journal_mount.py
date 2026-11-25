"""Finite Linux file-bind publication for an archive-backed legacy rollback.

Only the installed Root controller selects paths. Holding both file descriptors
prevents a mutable target directory from redirecting the privileged mount through
a substituted symlink. This module is not a general mount or command interface.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import stat

def identity(meta):return (meta.st_dev,meta.st_ino)

def bind_database(source,target,*,writer_uid=1000):
 if os.geteuid()!=0:raise PermissionError("JOURNAL_ROLLBACK_MOUNT_ROOT_REQUIRED")
 if os.stat("/proc/self/ns/mnt").st_ino!=os.stat("/proc/1/ns/mnt").st_ino:
  raise PermissionError("JOURNAL_ROLLBACK_HOST_MOUNT_NAMESPACE_REQUIRED")
 source,target=Path(source),Path(target)
 descriptors=[]
 try:
  for path in (source,target):
   fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);descriptors.append(fd)
   meta=os.fstat(fd)
   if (not stat.S_ISREG(meta.st_mode) or meta.st_uid!=writer_uid or meta.st_gid!=writer_uid
       or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o600):
    raise PermissionError("JOURNAL_ROLLBACK_MOUNT_FILE_IDENTITY")
  original=os.fstat(descriptors[0]);before=os.fstat(descriptors[1])
  if identity(source.lstat())!=identity(original) or identity(target.lstat())!=identity(before):
   raise PermissionError("JOURNAL_ROLLBACK_MOUNT_PATH_CHANGED")
  library=ctypes.CDLL(None,use_errno=True)
  mount=library.mount
  mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
  mount.restype=ctypes.c_int
  # Kernel resolves these already-open descriptors, never a caller-supplied
  # symlink in the mutable canonical data directory.
  source_fd=f"/proc/self/fd/{descriptors[0]}".encode()
  target_fd=f"/proc/self/fd/{descriptors[1]}".encode()
  if mount(source_fd,target_fd,None,4096,None)!=0:
   raise OSError(ctypes.get_errno(),"JOURNAL_ROLLBACK_FILE_BIND_FAILED")
  if identity(target.lstat())!=identity(original):
   raise RuntimeError("JOURNAL_ROLLBACK_MOUNT_READBACK_FAILED")
  return {"status":"archive_database_bound_to_canonical_file",
          "source_device":original.st_dev,"source_inode":original.st_ino}
 finally:
  for fd in descriptors:os.close(fd)
