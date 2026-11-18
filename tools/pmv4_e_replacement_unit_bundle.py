#!/usr/bin/env python3
"""Source-only systemd replacements, retaining approved existing backends.

This is NOT a production installer or evidence of new root-host reconcile
parity. Every service ExecCondition requires independently root-accepted Stage E
retirement marker. Backend legacy dependencies must be replaced before
the exact final authenticated transition can issue that marker.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import stat
from typing import Mapping

from tools import pmv4_e_scheduler_parity as parity

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path("infrastructure/openclaw-operations/systemd")
TARGET=Path("infrastructure/pmv4-e-scheduler/systemd")
ADMISSION="/opt/jason/pmv4-e-trusted/tools/pmv4_e_unit_admission.py"
# Mirror mandatory live production drop-ins when replacing service identities.
# New names do not inherit the legacy .service.d/ controls.
OWNER_PAUSE_CONDITION=(
    "ConditionPathExists=!/var/lib/jason/openclaw/support-repair/"
    "pmv3-engineering-owner-pause.json\n"
)
RELEASE_HOLD_CONDITION=(
    "ConditionPathExists=!/var/lib/jason/openclaw/release-manager/"
    "auto-promotion-incident-hold\n"
)
DRIFT_PREFLIGHT_CONDITION=(
    'ExecCondition=/usr/bin/python3 -c "import datetime,json,sys;'
    "from pathlib import Path;"
    "p=Path('/var/lib/jason/openclaw/release-manager/"
    "protected-readback/production-drift.json');"
    "d=json.loads(p.read_text());"
    "age=(datetime.datetime.now(datetime.timezone.utc)-"
    "datetime.datetime.fromisoformat(d['observed_at'].replace("
    "'Z','+00:00'))).total_seconds();"
    "sys.exit(0 if d.get('status')=='pass' and not d.get('problems')"
    ' and 0<=age<=120 else 1)"\n'
)


class PMv4EUnitBundleDenied(PermissionError):
    pass


def need(ok:bool,why:str)->None:
    if not ok:raise PMv4EUnitBundleDenied("PMV4_E_BUNDLE_"+why)


@dataclass(frozen=True)
class Pair:
    side:str
    old_prefix:str
    new_prefix:str
    trigger:str
    mode:str

    @property
    def old_service(self):
        return self.old_prefix+".service"

    @property
    def new_service(self):
        return self.new_prefix+".service"

    @property
    def old_trigger(self):
        return self.old_prefix+"."+self.trigger

    @property
    def new_trigger(self):
        return self.new_prefix+"."+self.trigger


PAIRS=(
    Pair("user","jason-support-repair-worker","jason-pmv4-engineering",
         "timer","engineering"),
    Pair("user","jason-release-approval-only","jason-pmv4-release-approval",
         "timer","release-approval"),
    Pair("user","jason-release-manager","jason-pmv4-component-release",
         "timer","component-release"),
    Pair("system","jason-release-control-transition","jason-pmv4-component-transition",
         "timer","component-transition"),
    Pair("system","jason-release-control-readback","jason-pmv4-component-readback",
         "timer","component-readback"),
    Pair("system","jason-release-host-reconcile","jason-pmv4-component-reconcile",
         "path","component-reconcile"),
)
USER_NEW={p.new_trigger for p in PAIRS if p.side=="user"}
SYSTEM_NEW={p.new_trigger for p in PAIRS if p.side=="system"}
need(USER_NEW==parity.USER_REPLACEMENT and SYSTEM_NEW==parity.ROOT_REPLACEMENT,
     "PUBLISHED_SIX_UNIT_POLICY_MISMATCH")


def safe_source(base:Path,side:str,name:str)->bytes:
    need(side in ("user","system")
         and re.fullmatch(r"jason-[a-z0-9-]+\.(service|timer|path)",name)
             is not None,
         "SOURCE_UNIT_OUTSIDE_ALLOWLIST")
    directory=SOURCE/("user" if side=="user" else "")
    path=base/directory/name
    try:
        meta=path.lstat()
        need(not path.is_symlink()
             and stat.S_ISREG(meta.st_mode)
             and meta.st_size>0 and meta.st_size<25000
             and meta.st_mode&0o002==0,
             "LEGACY_UNIT_FILE_UNTRUSTED")
        return path.read_bytes()
    except OSError as exc:
        raise PMv4EUnitBundleDenied("PMV4_E_BUNDLE_LEGACY_UNIT_MISSING") from exc


def generate(*,base:Path=ROOT)->dict[str,bytes]:
    need(base.is_dir(),"SOURCE_ROOT_NOT_PRESENT")
    out={}
    for pair in PAIRS:
        path=TARGET/("user" if pair.side=="user" else "system")
        old_service=safe_source(base,pair.side,pair.old_service)
        old_trigger=safe_source(base,pair.side,pair.old_trigger)
        try:
            service=old_service.decode("utf-8")
            trigger=old_trigger.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PMv4EUnitBundleDenied("PMV4_E_BUNDLE_NONUTF8_UNIT") from exc
        need(service.count("[Service]")==1
             and service.count("ExecStart=")==1
             and service.count("Type=oneshot")==1
             and "ExecCondition=/usr/bin/python3 "+ADMISSION not in service,
             "LEGACY_SERVICE_FORMAT_CHANGED")
        guard=("ExecCondition=/usr/bin/python3 "+ADMISSION+
               " --mode "+pair.mode+"\n")
        service=service.replace("[Service]\n","[Service]\n"+guard,1)
        if pair.mode=="engineering":
            service=service.replace("[Unit]\n",
                                    "[Unit]\n"+OWNER_PAUSE_CONDITION,1)
        elif pair.mode=="component-release":
            service=service.replace("[Unit]\n",
                                    "[Unit]\n"+RELEASE_HOLD_CONDITION,1)
            service=service.replace("[Service]\n",
                                    "[Service]\n"+DRIFT_PREFLIGHT_CONDITION,1)
        need(trigger.count("Unit="+pair.old_service)==1
             and trigger.count("[Timer]" if pair.trigger=="timer" else "[Path]")==1,
             "LEGACY_TRIGGER_FORMAT_CHANGED")
        trigger=trigger.replace("Unit="+pair.old_service,
                                "Unit="+pair.new_service,1)
        new_service=path/pair.new_service
        new_trigger=path/pair.new_trigger
        need(str(new_service) not in out and str(new_trigger) not in out,
             "REPLACEMENT_UNIT_COLLISION")
        out[str(new_service)]=service.encode("utf-8")
        out[str(new_trigger)]=trigger.encode("utf-8")
    need(len(out)==12,"EXACT_SIX_TRIGGER_SIX_SERVICE_SET_MISSING")
    return out


def validate(*,base:Path=ROOT)->dict:
    generated=generate(base=base)
    for name,data in generated.items():
        source=(base/name).read_bytes()
        need(source==data,"REVIEWED_REPLACEMENT_UNIT_DIFFERS:"+name)
    return {
        "status":"source_only_units_reviewed_no_production_install",
        "source_unit_count":12,
        "trigger_count":6,
        "service_count":6,
        "legacy_backend_execstart_changed":False,
        "guarded_by_future_exact_root_acceptance":True,
        "self_heal_and_reconcile_migration_accepted":False,
        "root_install_authorized":False,
        "pmv3_retirement_authorized":False,
        "production_mutations":False,
        "source_sha256":{
            name:sha256(data).hexdigest()
            for name,data in sorted(generated.items())},
    }


if __name__=="__main__":
    import json
    print(json.dumps(validate(),sort_keys=True))
