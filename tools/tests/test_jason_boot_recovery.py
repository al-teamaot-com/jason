from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'tools/jason_boot_recovery.py'
spec=importlib.util.spec_from_file_location('boot_recovery_tested',SCRIPT)
mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)


def write(path: Path, value: bytes, mode: int, uid: int | None=None, gid: int | None=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(value); path.chmod(mode)
    if uid is not None:
        path.chown(uid, gid if gid is not None else -1)


def test_current_credentials_do_not_refresh(tmp_path):
    pairs=[]
    for provider in ('autotask','it-glue'):
        for name in ('role','secret'):
            src=tmp_path/'src'/provider/name
            dst=tmp_path/'dst'/provider/name
            write(src,(provider+name).encode(),0o600)
            write(dst,(provider+name).encode(),0o400)
            pairs.append((src,dst))
    with (
        patch.object(mod,'BOOTSTRAP_TO_STAGED',tuple(pairs)),
        patch.object(mod,'STAGED_FILES',tuple(dst for _,dst in pairs)),
        patch.object(mod.os,'geteuid',return_value=0),
        patch.object(mod.os,'lstat',side_effect=lambda p: _fake_lstat(Path(p), pairs)),
    ):
        assert mod.staged_credentials_current() is True


def _fake_lstat(path: Path, pairs):
    st=path.stat()
    source={a for a,_ in pairs}
    uid=0 if path in source else 1000
    gid=0 if path in source else 1000
    return SimpleNamespace(st_mode=st.st_mode,st_uid=uid,st_gid=gid,st_size=st.st_size,st_ino=st.st_ino,st_dev=st.st_dev)


def test_mismatch_is_detected_without_printing_values(tmp_path):
    pairs=[]
    for i in range(4):
        src=tmp_path/'src'/str(i); dst=tmp_path/'dst'/str(i)
        write(src,b'authoritative-'+bytes([48+i]),0o600)
        write(dst,b'authoritative-'+bytes([48+i]),0o400)
        pairs.append((src,dst))
    pairs[-1][1].chmod(0o600); pairs[-1][1].write_bytes(b'stale-runtime-value'); pairs[-1][1].chmod(0o400)
    with (
        patch.object(mod,'BOOTSTRAP_TO_STAGED',tuple(pairs)),
        patch.object(mod,'STAGED_FILES',tuple(dst for _,dst in pairs)),
        patch.object(mod.os,'lstat',side_effect=lambda p: _fake_lstat(Path(p), pairs)),
    ):
        assert mod.staged_credentials_current() is False


def test_stage_refresh_requests_replace_and_remount_is_separate(tmp_path):
    stager=tmp_path/'stager.py'; stager.write_text('# stub')
    with (
        patch.object(mod,'STAGER',stager),
        patch.object(mod,'STAGED_FILES',(tmp_path/'existing',)),
        patch.object(Path,'exists',return_value=True),
        patch.object(mod,'staged_credentials_ready',return_value=True),
        patch.object(mod,'staged_credentials_current',side_effect=[False,True]),
        patch.object(mod,'run',return_value=SimpleNamespace(returncode=0)) as run,
    ):
        assert mod.stage_runtime_credentials() is True
    args=run.call_args.args[0]
    assert '--replace-existing' in args
    assert '--stage' in args


def test_runtime_remount_reuses_exact_live_image_and_revision(tmp_path):
    helper=tmp_path/'deploy_live_container.py'; helper.write_text('# stub')
    inspect=[{'Image':'sha256:'+'a'*64,'Config':{'Labels':{'com.teamaot.jason.source_revision':'b'*40}}}]
    calls=[]
    def fake_run(args,quiet=False):
        calls.append(args)
        if args[:2]==['docker','inspect']:
            import json
            return SimpleNamespace(returncode=0,stdout=json.dumps(inspect))
        return SimpleNamespace(returncode=0,stdout='')
    with patch.object(mod,'LIVE_DEPLOY',helper), patch.object(mod,'run',side_effect=fake_run):
        mod.recreate_runtime_for_credential_refresh()
    deploy=next(call for call in calls if '--live' in call)
    assert deploy[deploy.index('--image')+1]=='sha256:'+'a'*64
    assert deploy[deploy.index('--source-revision')+1]=='b'*40
    assert '--harden' in deploy
    assert calls[-1][0:2]==['docker','rm']
    assert calls[-1][2].startswith('jason-runtime-credential-refresh-')
