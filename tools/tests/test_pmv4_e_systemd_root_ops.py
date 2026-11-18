"""Provider-free exact systemd adapter tests using disposable unit directories."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_e_systemd_root_ops as ops
from tools import pmv4_e_replacement_unit_bundle as bundle


class FakeSystemctl:
    def __init__(self):
        self.active=set(ops.OLD_USER|ops.OLD_ROOT)
        self.enabled=set(ops.OLD_USER|ops.OLD_ROOT)
        self.calls=[]

    def __call__(self,argv,**kw):
        assert kw["capture_output"] is True
        self.calls.append(tuple(argv))
        user="/usr/sbin/runuser" in argv
        idx=argv.index("/usr/bin/systemctl") if user else 0
        params=argv[idx+1:]
        if user:
            assert params[0]=="--user"
            params=params[1:]
        action=params[0]
        assert action in {"is-active","is-enabled","start","stop",
                          "enable","disable","daemon-reload"}
        names=params[1:]
        if action=="daemon-reload":
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        assert len(names)==1
        name=names[0]
        if action=="is-active":
            status="active" if name in self.active else "inactive"
            return SimpleNamespace(returncode=0 if name in self.active else 3,
                                   stdout=status+"\n",stderr="")
        if action=="is-enabled":
            status="enabled" if name in self.enabled else "disabled"
            return SimpleNamespace(returncode=0 if name in self.enabled else 1,
                                   stdout=status+"\n",stderr="")
        if action=="start":
            self.active.add(name)
        elif action=="stop":
            self.active.discard(name)
        elif action=="enable":
            self.enabled.add(name)
        elif action=="disable":
            self.enabled.discard(name)
        return SimpleNamespace(returncode=0,stdout="",stderr="")


def make(tmp_path,monkeypatch):
    u=tmp_path/"user"
    s=tmp_path/"system"
    u.mkdir()
    s.mkdir()
    trusted=tmp_path/"trust/infrastructure/pmv4-e-scheduler/systemd"
    trusted.mkdir(parents=True)
    generated={}
    for p in bundle.PAIRS:
        side="user" if p.side=="user" else "system"
        for name in (p.new_trigger,p.new_service):
            path=f"infrastructure/pmv4-e-scheduler/systemd/{side}/{name}"
            generated[path]=(name+"\n").encode()
    assert len(generated)==12
    monkeypatch.setattr(ops.bundle,"generate",lambda *,base:generated)
    hashes={name:sha256(data).hexdigest() for name,data in generated.items()}
    fake=FakeSystemctl()
    root=ops.ExactSystemdSurface(production=False,
           runner=fake,user_dir=u,system_dir=s,trusted_dir=trusted)
    return root,fake,hashes,generated,u,s


def test_exact_twelve_sources_staged_and_cleanly_removed(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    installed=root.stage(hashes)
    assert len(installed)==12
    assert all(Path(p).is_file() for p in installed)
    assert all(Path(p).stat().st_mode&0o777==0o644 for p in installed)
    assert fake.active==set(ops.OLD_USER|ops.OLD_ROOT)
    assert len([x for x in fake.calls if x[-1]=="daemon-reload"])==2
    root.unstage_exact(hashes)
    assert all(not Path(p).exists() for p in installed)


def test_approved_legacy_stop_six_and_activate_exact_new(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    root.stage(hashes)
    root.disable_legacy()
    assert not fake.active
    assert not fake.enabled
    root.activate_replacement()
    assert fake.active==set(ops.NEW_USER|ops.NEW_ROOT)
    assert fake.enabled==set(ops.NEW_USER|ops.NEW_ROOT)
    assert root.verify_final(replacement=True)
    root.restore_legacy()
    assert root.verify_final(replacement=False)
    root.unstage_exact(hashes)


def test_wrong_hash_or_extra_source_never_install(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    modified=dict(hashes)
    modified[next(iter(modified))]="0"*64
    with pytest.raises(ops.StageESystemdDenied,match="REVIEWED_UNIT_DIGEST_CHANGED"):
        root.stage(modified)
    with pytest.raises(ops.StageESystemdDenied,match="EXACT_UNIT_HASH_SET_REQUIRED"):
        root.stage({**hashes,"out-of-scope.service":"f"*64})


def test_existing_target_refused_without_overwrite(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    target=u/"jason-pmv4-engineering.timer"
    target.write_text("do not replace")
    with pytest.raises(ops.StageESystemdDenied,match="TARGET_ALREADY_EXISTS"):
        root.stage(hashes)
    assert target.read_text()=="do not replace"


def test_staging_partial_failure_recovery_only_exact_bytes(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    target=u/"jason-pmv4-engineering.timer"
    target.write_text("modified")
    with pytest.raises(ops.StageESystemdDenied,match="TARGET_ALREADY_EXISTS"):
        root.stage(hashes)
    with pytest.raises(ops.StageESystemdDenied,match="ROLLBACK_UNIT_DRIFT"):
        root.unstage_exact(hashes)
    assert target.read_text()=="modified"


def test_unreviewed_systemctl_target_and_verb_denied(tmp_path,monkeypatch):
    root,fake,*_=make(tmp_path,monkeypatch)
    with pytest.raises(ops.StageESystemdDenied,match="OUT_OF_SCOPE_UNIT"):
        root._call(user=False,action="stop",names=("jason-core.service",))
    with pytest.raises(ops.StageESystemdDenied,match="UNREVIEWED_SYSTEMD_VERB"):
        root._call(user=False,action="restart",names=("jason-release-manager.timer",))


def test_stage_missing_six_reviewed_unit_files_denied(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    monkeypatch.setattr(ops.bundle,"generate",lambda *,base:dict(list(generated.items())[:11]))
    with pytest.raises(ops.StageESystemdDenied,match="EXACT_UNIT_HASH_SET_REQUIRED"):
        root.stage(hashes)


def test_new_timer_cannot_pass_postflight_while_legacy_still_active(tmp_path,monkeypatch):
    root,fake,hashes,generated,u,s=make(tmp_path,monkeypatch)
    root.stage(hashes)
    root.activate_replacement()
    assert root.verify_final(replacement=True) is False


def test_source_has_no_unreviewed_shell_provider_or_host_reboot():
    c=(Path(__file__).resolve().parents[2]/"tools/pmv4_e_systemd_root_ops.py").read_text()
    for forbidden in ("shell=True","os.system(","docker restart","systemctl reboot",
                      "subprocess.Popen(","requests.post(","/bin/sh","sudo "):
        assert forbidden not in c
