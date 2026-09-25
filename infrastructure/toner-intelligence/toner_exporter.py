#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import toner_metrics
import toner_snapshot

HOST=os.environ.get('JASON_TONER_EXPORTER_HOST','0.0.0.0')
PORT=int(os.environ.get('JASON_TONER_EXPORTER_PORT','9473'))
REFRESH_SECONDS=int(os.environ.get('JASON_TONER_REFRESH_SECONDS','900'))
SNAPSHOT=Path(os.environ.get('JASON_TONER_SNAPSHOT','/var/lib/jason/toner-intelligence/snapshot.json'))
_lock=threading.Lock()
_metrics=''
_last_success=0.0
_refresh_ok=0
_last_error='not yet refreshed'


def refresh() -> None:
    global _metrics,_last_success,_refresh_ok,_last_error
    try:
        SNAPSHOT.parent.mkdir(parents=True,exist_ok=True)
        with contextlib.redirect_stdout(io.StringIO()):
            toner_snapshot.main(str(SNAPSHOT))
        body=toner_metrics.render(str(SNAPSHOT))
        now=time.time()
        with _lock:
            _metrics=body; _last_success=now; _refresh_ok=1; _last_error=''
    except Exception as exc:
        with _lock:
            _refresh_ok=0; _last_error=f'{type(exc).__name__}: {exc}'[:300]


def refresher() -> None:
    while True:
        refresh()
        time.sleep(max(60,REFRESH_SECONDS))


def render() -> str:
    with _lock:
        health=(
            '# HELP jason_toner_exporter_refresh_success Whether the most recent toner refresh succeeded.\n'
            '# TYPE jason_toner_exporter_refresh_success gauge\n'
            f'jason_toner_exporter_refresh_success {_refresh_ok}\n'
            '# HELP jason_toner_exporter_last_success_timestamp_seconds Unix time of last successful toner refresh.\n'
            '# TYPE jason_toner_exporter_last_success_timestamp_seconds gauge\n'
            f'jason_toner_exporter_last_success_timestamp_seconds {_last_success:.3f}\n'
        )
        return health+_metrics


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {'/','/metrics'}:
            self.send_response(404); self.end_headers(); return
        body=render().encode()
        self.send_response(200)
        self.send_header('Content-Type','text/plain; version=0.0.4; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass


if __name__=='__main__':
    refresh()
    threading.Thread(target=refresher,daemon=True).start()
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
