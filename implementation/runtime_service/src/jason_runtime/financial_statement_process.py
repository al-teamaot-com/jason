"""Independent host for the existing governed financial maintenance component.

Does not import shared runtime composition, start HTTP/ticket workers or touch
production state. Configuration and boundary snapshot are read-only mounts;
state/audit/ownership lock are in this component's own volume.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import logging
import os
import signal
import sqlite3
import time
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from connectors.core.http_transport import UrlLibJsonHttpTransport
from orchestrator.event_store import SQLiteOrchestrationEventStore
from .financial_statement_composition import build_financial_statement_maintenance

STATE = Path('/var/lib/jason/financial-statements')
CONFIG = Path('/etc/jason/financial-statements/config.json')


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text())
    required = {'enabled', 'tenant_id', 'drive_id', 'root_path', 'timezone', 'run_hour',
                'boundary_snapshot', 'openbao_url', 'role_id_path', 'secret_id_path'}
    if set(cfg) != required:
        raise ValueError('exact component configuration keys required')
    if type(cfg['enabled']) is not bool:
        raise ValueError('enabled must be boolean')
    UUID(cfg['tenant_id'])
    if not isinstance(cfg['drive_id'], str) or not cfg['drive_id'].strip():
        raise ValueError('drive_id required')
    if cfg['root_path'] != 'Bank Checking Accounts Register':
        raise ValueError('unapproved intake root')
    if type(cfg['run_hour']) is not int or not 0 <= cfg['run_hour'] <= 23:
        raise ValueError('invalid local run hour')
    ZoneInfo(cfg['timezone'])
    for key in ('boundary_snapshot','role_id_path','secret_id_path'):
        if not isinstance(cfg[key],str) or not Path(cfg[key]).is_absolute():
            raise ValueError('absolute input paths required')
    return cfg


def build_worker(cfg: dict, state: Path):
    # Copy only the governed boundary snapshot into component-owned scratch.
    # Never open/migrate the running runtime's boundary database for writes.
    source = Path(cfg['boundary_snapshot'])
    if not source.is_file():
        raise ValueError('provisioned boundary snapshot required')
    with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as src:
        records = src.execute("SELECT external_tenant_id,profile,status FROM client_boundaries WHERE provider='microsoft_sharepoint'").fetchall()
        if records != [(cfg['tenant_id'], 'sharepoint-write', 'validated')]:
            raise ValueError('exact validated tenant/writer boundary required')
        with sqlite3.connect(state/'boundary.sqlite3') as dst:
            src.backup(dst)
    audit = SQLiteOrchestrationEventStore(state/'orchestration-events.sqlite3')
    return build_financial_statement_maintenance(
        enabled=True, boundary_db=state/'boundary.sqlite3',
        openbao_url=cfg['openbao_url'], role_id_path=Path(cfg['role_id_path']),
        secret_id_path=Path(cfg['secret_id_path']), transport=UrlLibJsonHttpTransport(),
        state_db=state/'maintenance.sqlite3', tenant_id=cfg['tenant_id'],
        drive_id=cfg['drive_id'], root_path=cfg['root_path'],
        timezone_name=cfg['timezone'], run_hour=cfg['run_hour'], audit=audit)


def preflight(worker) -> dict:
    # Read-only provider acceptance; no folders, moves or run-completion record.
    root = worker.client.get_item_by_path(tenant_id=worker.tenant_id,
        drive_id=worker.drive_id, path=worker.root_path)
    if not root.get('id') or not isinstance(root.get('folder'),dict):
        raise ValueError('approved intake is not a folder')
    children = worker.client.list_children(tenant_id=worker.tenant_id,
        drive_id=worker.drive_id,item_id=root['id'])
    return {'status':'read_verified','root_id':root['id'],'children':len(children),
            'provider_mutations':0,'scheduled_run_verified':False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=CONFIG)
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args(argv)
    cfg=load_config(args.config)
    if not cfg['enabled'] and not args.preflight:
        raise SystemExit('financial statement component disabled')
    os.umask(0o077)
    STATE.mkdir(parents=True,exist_ok=True)
    # One process owns this component; a second instance must never race moves.
    with (STATE/'process.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=build_worker(cfg,STATE)
        if args.preflight:
            print(json.dumps(preflight(worker),sort_keys=True));return
        stopping=False
        def stop(*_):
            nonlocal stopping
            stopping=True
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        while not stopping:
            try:
                if worker.tick():
                    print(json.dumps({'event':'financial_statement_tick_finished'}),flush=True)
            except Exception as exc:
                # Avoid leaking provider response bodies or document content.
                logging.error('financial statement cycle failed: %s',type(exc).__name__)
            for _ in range(60):
                if stopping:break
                time.sleep(1)

if __name__=='__main__':
    main()
