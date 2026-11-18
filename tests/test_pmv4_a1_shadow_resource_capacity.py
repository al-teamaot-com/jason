"""One bounded isolated A1 resource/health correction; no security expansion."""
from pathlib import Path
import subprocess
import re
import os
import json

import pytest

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"config/pmv4-shadow/docker-compose.yml"
BASE="8c2064193d74cc41b52369681febbc0a74fa96f7"

EXACT={
    '    pids_limit: 64':'    pids_limit: 256',
    '    mem_limit: "512m"':'    mem_limit: "4g"',
    '    cpus: "0.5"':'    cpus: "1.0"',
    '      timeout: 8s':'      timeout: 15s',
    '      start_period: 60s':'      start_period: 120s',
}


def original():
    q=subprocess.run(["git","-C",str(ROOT),"show",
                      BASE+":config/pmv4-shadow/docker-compose.yml"],
                     capture_output=True,text=True,check=True,timeout=12)
    return q.stdout


def test_exact_five_resource_and_wait_values_no_other_changes():
    before=original()
    after=CONFIG.read_text()
    for old,new in EXACT.items():
        assert before.count(old)==1,old
        before=before.replace(old,new)
    assert after==before
    for must in (
        'network_mode: "none"', 'ports: []', 'user: "1000:1000"',
        'read_only: true', 'cap_drop: ["ALL"]',
        'security_opt: ["no-new-privileges:true"]',
        'restart: "no"', 'OPENCLAW_GATEWAY_TOKEN:',
        '    volumes:', '    tmpfs:', '    image: "$PMV4_SHADOW_IMAGE_SHA"',
    ):
        assert must in after
    for prohibited in ("privileged: true","network_mode: host",
                       "/var/lib/jason/openclaw","/var/run/docker.sock",
                       "AWS_SECRET_ACCESS_KEY","AUTOTASK_API_KEY"):
        assert prohibited not in after


def test_isolated_4gb_256pids_remains_bounded():
    src=CONFIG.read_text()
    assert 'pids_limit: 256' in src
    assert 'mem_limit: "4g"' in src
    assert 'cpus: "1.0"' in src
    assert 'timeout: 15s' in src
    assert 'start_period: 120s' in src


def test_compose_dry_run_requires_no_real_provider_token_or_live_changes():
    source=CONFIG
    environment={
        "PATH":"/usr/bin:/bin",
        "PMV4_SHADOW_IMAGE_SHA":"sha256:"+"a"*64,
        "PMV4_SHADOW_GATEWAY_TOKEN":"synthetic-recovery-profile-only",
    }
    process=subprocess.run(
        ["/usr/bin/docker","compose",
         "--project-name","jason-pmv4-shadow-capacity-test",
         "-f",str(source),"config","--format","json"],
        env=environment,capture_output=True,text=True,check=False,timeout=20)
    assert process.returncode==0,process.stderr[:400]
    config=json.loads(process.stdout)["services"]["pmv4-shadow-gateway"]
    assert config["network_mode"]=="none"
    assert config["read_only"] is True
    assert config["pids_limit"]==256
    assert int(config["mem_limit"])==4294967296
    assert config["cpus"]==1.0
    assert config["restart"]=="no"
    assert config["user"]=="1000:1000"
    assert config["privileged"] is False if "privileged" in config else True



def test_only_memory_limit_increases_from_deployed_protected_source():
    base="e88befc72cb3600702e3492246b1b44dc10294e0"
    previous=subprocess.run(
        ["git","-C",str(ROOT),"show",base+":config/pmv4-shadow/docker-compose.yml"],
        capture_output=True,text=True,check=True,timeout=12).stdout
    assert previous.count('    mem_limit: "2g"')==1
    expected=previous.replace('    mem_limit: "2g"','    mem_limit: "4g"')
    assert CONFIG.read_text()==expected
    assert expected.count('network_mode: "none"')==1
    assert expected.count('    restart: "no"')==1
    assert '    mem_limit: "4g"' in expected
