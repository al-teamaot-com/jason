#!/usr/bin/env python3
from __future__ import annotations
import json, os
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
DIR=Path(os.environ.get("JASON_CLIENT_POSTURE_DIR","/var/lib/jason/client-posture"))
HOST=os.environ.get("JASON_CLIENT_POSTURE_EXPORTER_HOST","0.0.0.0")
PORT=int(os.environ.get("JASON_CLIENT_POSTURE_EXPORTER_PORT","9472"))
STATES=("confirmed_good","confirmed_gap","unknown","not_applicable","evidence_unavailable")
def metrics(directory: Path|None=None):
    root=directory or DIR; available=1 if root.exists() and root.is_dir() else 0; reviews=0; counts=Counter(); latest=""
    if available:
      for p in sorted(root.glob("*.json")):
       try: d=json.loads(p.read_text()); reviews+=1; latest=max(latest,str(d.get("reviewed_at",''))); [counts.update([str(x.get("state"))]) for x in d.get("assessments",[]) if str(x.get("state")) in STATES]
       except (OSError,ValueError,TypeError): continue
    lines=["# HELP jason_client_posture_available Client posture durable report directory readable.","# TYPE jason_client_posture_available gauge",f"jason_client_posture_available {available}","# HELP jason_client_posture_reviews Number of durable client posture review snapshots.","# TYPE jason_client_posture_reviews gauge",f"jason_client_posture_reviews {reviews}","# HELP jason_client_posture_controls Aggregate control classifications across durable review snapshots.","# TYPE jason_client_posture_controls gauge"]
    lines += [f'jason_client_posture_controls{{state="{s}"}} {counts[s]}' for s in STATES]
    lines += ["# HELP jason_client_posture_latest_review_info Presence of at least one review; timestamp is intentionally not a label.","# TYPE jason_client_posture_latest_review_info gauge",f"jason_client_posture_latest_review_info {1 if latest else 0}",""]
    return "\n".join(lines)
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in {"/","/metrics"}: self.send_response(404); self.end_headers(); return
  b=metrics().encode(); self.send_response(200); self.send_header("Content-Type","text/plain; version=0.0.4"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,*args): pass
if __name__=="__main__": HTTPServer((HOST,PORT),H).serve_forever()
