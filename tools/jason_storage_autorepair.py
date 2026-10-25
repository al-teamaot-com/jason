"""Governed, non-disruptive two-drive capacity autorepair.

Only cold, *clean, detached*, merged Git worktrees are tar-archived on a
separate verified volume, independently verified and then retired with Git's
own unforced worktree removal. Never changes an active audit/SQLite file,
container, Docker image/volume, backup, approval record, or production release.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('/var/lib/jason/openclaw/self-heal')
POLICY = Path(__file__).resolve().parents[1] / 'config/operations/host-storage-autorepair-v1.json'
MAIN_REPO = Path('/home/al/projects/jason')
GIB = 1024 ** 3
SHA = re.compile(r'[a-f0-9]{40}\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{3,140}\Z')


def policy(path: Path = POLICY) -> dict[str, Any]:
    p = json.loads(path.read_text(encoding='utf-8'))
    if (set(p) != {'schema_version','enabled','owner_authority','intervention_used_percent',
                   'destination_max_used_percent','minimum_age_days','max_worktrees_per_cycle',
                   'max_bytes_per_cycle','max_bytes_per_worktree','source_worktree_root',
                   'archive_worktree_root','archive_mount','protected_paths','allow_actions',
                   'require_ancestor_of_protected_main','no_service_signals','no_live_data_mutations'}
            or p['schema_version'] != '1.0' or p['enabled'] is not True
            or p['owner_authority'] != 'owner-2026-10-25-conditional-dual-drive-safe-maintenance'
            or p['source_worktree_root'] != '/home/al/jason-worktrees'
            or p['archive_worktree_root'] != '/srv/jason/archive/historical/retired-git-worktrees/auto'
            or p['archive_mount'] != '/srv/jason/archive'
            or p['protected_paths'] != ['/var/lib/jason','/opt/jason','/var/lib/docker','/opt/jason/infrastructure/openbao/audit']
            or p['allow_actions'] != ['archive_reconstructible_clean_detached_worktree']
            or p['require_ancestor_of_protected_main'] is not True
            or p['no_service_signals'] is not True or p['no_live_data_mutations'] is not True):
        raise ValueError('unreviewed storage autonomy policy')
    bounds={'intervention_used_percent':(80,80),'destination_max_used_percent':(80,80),
            'minimum_age_days':(21,90),'max_worktrees_per_cycle':(1,10),
            'max_bytes_per_cycle':(1,536870912),'max_bytes_per_worktree':(1,134217728)}
    for key,(low,high) in bounds.items():
        if type(p[key]) is not int or not low<=p[key]<=high:
            raise ValueError('storage autorepair parameter outside reviewed bounds')
    return p


def usage(path: Path) -> tuple[float,int,int]:
    s=os.statvfs(path)
    block=int(s.f_frsize or s.f_bsize)
    used=(int(s.f_blocks)-int(s.f_bfree))*block
    available=int(s.f_bavail)*block
    if used<0 or available<0 or used+available<=0:
        raise ValueError('invalid capacity counters')
    return 100.0*used/(used+available),available,used+available


def capacity_gate(p: dict[str,Any]) -> tuple[str,dict[str,Any]]:
    src=Path(p['source_worktree_root']); dst=Path(p['archive_mount'])
    if (not os.path.ismount('/') or not os.path.ismount(dst)
            or not src.is_dir() or not dst.is_dir()
            or src.stat().st_dev == dst.stat().st_dev):
        return 'blocked_missing_independent_archive',{}
    a=usage(Path('/')); b=usage(dst)
    evidence={'root_percent':round(a[0],2),'archive_percent':round(b[0],2),
              'root_allocatable_gib':round(a[1]/GIB,2),
              'archive_allocatable_gib':round(b[1]/GIB,2)}
    if a[0]>=80 and b[0]>=80:
        return 'both_drives_80_owner_capacity_review',evidence
    if a[0]<80:
        return 'root_below_80',evidence
    archive_stat=os.statvfs(dst)
    if (b[0]>=80 or b[1]<20*GIB or
            (archive_stat.f_files>0 and archive_stat.f_favail<10000)):
        return 'blocked_archive_headroom',evidence
    return 'repair_allowed',evidence


def git(*args: str, cwd: Path = MAIN_REPO, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git','-C',str(cwd),*args],text=True,
                          capture_output=True,timeout=timeout,check=False)


def candidates(src: Path, *, minimum_age_days: int = 21) -> list[tuple[Path,str]]:
    result=git('worktree','list','--porcelain')
    if result.returncode:
        raise RuntimeError('git worktree registry unavailable')
    selected=[]
    for entry in result.stdout.strip().split('\n\n'):
        fields=entry.splitlines()
        p_line=next((x[9:] for x in fields if x.startswith('worktree ')),None)
        sha_line=next((x[5:] for x in fields if x.startswith('HEAD ')),None)
        if not p_line or not sha_line or not SHA.fullmatch(sha_line):continue
        current=Path(p_line)
        if (current.parent!=src or not NAME.fullmatch(current.name)
                or 'detached' not in fields
                or any(x.startswith('locked') or x.startswith('prunable') for x in fields)
                or current.is_symlink() or not current.is_dir()
                or (time.time()-current.stat().st_mtime)<minimum_age_days*86400):
            continue
        selected.append((current,sha_line))
    return sorted(selected,key=lambda entry:entry[0].stat().st_mtime)


def active_reference(path: Path) -> bool:
    path_text=str(path)
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            cwd=os.readlink(p/'cwd')
            args=(p/'cmdline').read_bytes()[:25000].replace(b'\x00',b' ').decode('utf-8','replace')
        except (PermissionError,FileNotFoundError,ProcessLookupError,OSError):
            continue
        if cwd==path_text or cwd.startswith(path_text+'/') or path_text in args:
            return True
    return False


def qualified(path: Path, sha: str) -> bool:
    if not SHA.fullmatch(sha) or not path.is_dir() or path.is_symlink():return False
    if active_reference(path):return False
    if git('rev-parse','HEAD',cwd=path).stdout.strip()!=sha:return False
    if git('symbolic-ref','-q','HEAD',cwd=path).returncode==0:return False
    clean=git('status','--porcelain=1','--untracked-files=all',cwd=path)
    if clean.returncode or clean.stdout.strip():return False
    ignored=git('ls-files','--others','--ignored','--exclude-standard',cwd=path)
    if ignored.returncode or ignored.stdout.strip():return False
    if git('merge-base','--is-ancestor',sha,'origin/main').returncode:return False
    return True


def size_bytes(path: Path, *, limit: int) -> int:
    total=0
    for base,dirs,files in os.walk(path,followlinks=False):
        for name in files:
            obj=Path(base)/name
            total+=obj.lstat().st_size
            if total>limit:return total
    return total


def tar_snapshot(src: Path,destination: Path,sha: str) -> tuple[str,int]:
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError('immutable archive target already exists')
    fd,tmp=tempfile.mkstemp(prefix='.storage-archive-',dir=destination.parent)
    os.fchmod(fd,0o600)
    os.close(fd)
    try:
        with tarfile.open(tmp,mode='w',dereference=False) as tar:
            tar.add(src,arcname=src.name,recursive=True)
        with tarfile.open(tmp,mode='r') as tar:
            members=tar.getmembers()
            if (not members or any(not (m.name==src.name or m.name.startswith(src.name+'/')) for m in members)
                    or not any(m.name==src.name+'/.git' for m in members)):
                raise ValueError('archive tar structure verification failed')
        h=hashlib.sha256()
        with open(tmp,'rb') as stream:
            for block in iter(lambda:stream.read(2**20),b''):h.update(block)
        with open(tmp,'rb') as stream:os.fsync(stream.fileno())
        os.replace(tmp,destination)
        dirfd=os.open(destination.parent,os.O_RDONLY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        return h.hexdigest(),destination.stat().st_size
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def atomic_manifest(target: Path, data: dict[str,Any]) -> None:
    fd,tmp=tempfile.mkstemp(prefix='.storage-manifest-',dir=target.parent)
    try:
        with os.fdopen(fd,'w') as out:
            os.fchmod(out.fileno(),0o600)
            json.dump(data,out,sort_keys=True,indent=2)
            out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def repair(*, policy_path: Path=POLICY, dry_run: bool=False) -> dict[str,Any]:
    p=policy(policy_path)
    status,ev=capacity_gate(p)
    report={'schema_version':'1.0','status':status,'capacity':ev,'archived_count':0,'archived_bytes':0,'checked_at':datetime.now(timezone.utc).isoformat()}
    if status!='repair_allowed':return report
    if dry_run:
        report['status']='eligible_dry_run'
        report['candidate_count']=len(candidates(Path(p['source_worktree_root']),minimum_age_days=p['minimum_age_days']))
        return report
    dest=Path(p['archive_worktree_root'])
    dest.mkdir(parents=True,exist_ok=True,mode=0o700)
    if dest.is_symlink() or dest.stat().st_dev!=Path(p['archive_mount']).stat().st_dev:
        report['status']='archive_target_invalid';return report
    os.chmod(dest,0o700)
    lockpath=ROOT/'storage-autorepair.lock'
    lockpath.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with lockpath.open('a+') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            report['status']='already_running';return report
        for path,sha in candidates(Path(p['source_worktree_root']),minimum_age_days=p['minimum_age_days']):
            if report['archived_count']>=p['max_worktrees_per_cycle']:break
            capacity,ev=capacity_gate(p)
            if capacity!='repair_allowed':break
            if not qualified(path,sha):continue
            amount=size_bytes(path,limit=p['max_bytes_per_worktree'])
            if (amount<=0 or amount>p['max_bytes_per_worktree']
                    or amount+report['archived_bytes']>p['max_bytes_per_cycle']):continue
            dest_pct=100.0*(usage(Path(p['archive_mount']))[2]-usage(Path(p['archive_mount']))[1]+amount)/usage(Path(p['archive_mount']))[2]
            if dest_pct>=p['destination_max_used_percent'] or usage(Path(p['archive_mount']))[1]-amount<20*GIB:
                report['status']='blocked_archive_headroom';break
            snapshot=dest/(path.name+'-'+sha[:12]+'.tar')
            manifest=dest/(path.name+'-'+sha[:12]+'.json')
            if snapshot.exists() or manifest.exists():continue
            try:
                digest,archive_bytes=tar_snapshot(path,snapshot,sha)
                rec={'schema_version':'1.0','head':sha,'source':str(path),'archive':str(snapshot),
                     'sha256':digest,'bytes':archive_bytes,'status':'verified_archive_source_preserved',
                     'recorded_at':datetime.now(timezone.utc).isoformat()}
                atomic_manifest(manifest,rec)
                if not qualified(path,sha):continue
                done=git('worktree','remove',str(path),timeout=30)
                if done.returncode or path.exists():continue
                rec['status']='source_retired_by_git';rec['retired_at']=datetime.now(timezone.utc).isoformat()
                atomic_manifest(manifest,rec)
                report['archived_count']+=1;report['archived_bytes']+=archive_bytes
            except (OSError,ValueError,tarfile.TarError,subprocess.TimeoutExpired):
                report['status']='partial_archive_halted';break
        report['capacity_after']=capacity_gate(p)[1]
        if report['status']=='repair_allowed':
            report['status']='archived_and_verified' if report['archived_count'] else 'no_safe_cold_worktree_available'
        return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(repair(dry_run=args.dry_run),sort_keys=True))
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        print(json.dumps({'status':'blocked','error_type':type(error).__name__}))
        raise SystemExit(2)
