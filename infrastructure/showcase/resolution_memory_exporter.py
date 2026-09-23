#!/usr/bin/env python3
from __future__ import annotations
import os, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
DB=Path(os.environ.get("JASON_RESOLUTION_MEMORY_DB","/var/lib/jason/openclaw/resolution-memory.sqlite3"))
HOST=os.environ.get("JASON_RESOLUTION_MEMORY_EXPORTER_HOST","0.0.0.0")
PORT=int(os.environ.get("JASON_RESOLUTION_MEMORY_EXPORTER_PORT","9470"))
def metrics():
    available=0; total=0; verified=0; observed=0; deprecated=0; clients=0
    if DB.exists():
        try:
            c=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
            total=int(c.execute("select count(*) from resolution_cases").fetchone()[0])
            clients=int(c.execute("select count(distinct organization_id || char(31) || client_id) from resolution_cases").fetchone()[0])
            rows=dict(c.execute("select status,count(*) from resolution_cases group by status").fetchall())
            verified=int(rows.get("verified",0)); observed=int(rows.get("observed",0)); deprecated=int(rows.get("deprecated",0)); available=1; c.close()
        except sqlite3.Error: pass
    return "\n".join([
      "# HELP jason_resolution_memory_available Resolution Memory SQLite store readable.","# TYPE jason_resolution_memory_available gauge",f"jason_resolution_memory_available {available}",
      "# HELP jason_resolution_memory_cases Resolution Memory cases by status.","# TYPE jason_resolution_memory_cases gauge",f'jason_resolution_memory_cases{{status="all"}} {total}',f'jason_resolution_memory_cases{{status="verified"}} {verified}',f'jason_resolution_memory_cases{{status="observed"}} {observed}',f'jason_resolution_memory_cases{{status="deprecated"}} {deprecated}',
      "# HELP jason_resolution_memory_client_scopes Number of client-isolated scopes represented in memory.","# TYPE jason_resolution_memory_client_scopes gauge",f"jason_resolution_memory_client_scopes {clients}",""])
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/metrics","/"}: self.send_response(404); self.end_headers(); return
        body=metrics().encode(); self.send_response(200); self.send_header("Content-Type","text/plain; version=0.0.4"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
if __name__=="__main__": HTTPServer((HOST,PORT),H).serve_forever()
