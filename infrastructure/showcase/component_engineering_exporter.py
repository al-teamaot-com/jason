#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REQUESTS_PATH = Path(os.environ.get("JASON_COMPONENT_ENGINEERING_PATH", "/var/lib/jason/component-engineering/requests"))
HOST = os.environ.get("JASON_COMPONENT_ENGINEERING_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_COMPONENT_ENGINEERING_EXPORTER_PORT", "9472"))


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _load_requests(path: Path | None = None) -> list[dict]:
    root=path or REQUESTS_PATH
    if not root.exists() or not root.is_dir(): return []
    out=[]
    for candidate in sorted(root.glob("*.json")):
        try: item=json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError,ValueError,json.JSONDecodeError): continue
        if isinstance(item,dict) and str(item.get("request_id","")).strip(): out.append(item)
    return out


def render_metrics(*, requests_path: Path | None=None) -> str:
    rows=_load_requests(requests_path)
    terminal={"resolved","retired"}
    active=[r for r in rows if str(r.get("lifecycle","open")) not in terminal]
    lifecycle=Counter(str(r.get("lifecycle","unknown")) for r in rows)
    kind=Counter(str(r.get("kind","unknown")) for r in active)
    risk=Counter(str(r.get("risk","unknown")) for r in active)
    lines=[
      "# HELP jason_component_engineering_requests Number of durable Component Engineering requests.",
      "# TYPE jason_component_engineering_requests gauge",
      f"jason_component_engineering_requests {len(rows)}",
      "# HELP jason_component_engineering_active_requests Number of non-terminal Component Engineering requests.",
      "# TYPE jason_component_engineering_active_requests gauge",
      f"jason_component_engineering_active_requests {len(active)}",
      "# HELP jason_component_engineering_request_info Secret-safe metadata for durable engineering requests.",
      "# TYPE jason_component_engineering_request_info gauge",
      "# HELP jason_component_engineering_occurrences Operational occurrences attached to an engineering request.",
      "# TYPE jason_component_engineering_occurrences gauge",
    ]
    for row in rows:
        rid=str(row.get("request_id","unknown"))
        labels={
          "request_id":rid,
          "title":str(row.get("title","")),
          "problem_key":str(row.get("problem_key","")),
          "kind":str(row.get("kind","unknown")),
          "lifecycle":str(row.get("lifecycle","unknown")),
          "risk":str(row.get("risk","unknown")),
          "existing_component":str(row.get("existing_component_name","")),
          "proposed_component_name":str(row.get("proposed_component_name","")),
          "proposed_component_description":str(row.get("proposed_component_description","")),
          "owner":str(row.get("owner","")),
        }
        text=",".join(f'{k}="{_escape(v)}"' for k,v in labels.items())
        lines.append(f"jason_component_engineering_request_info{{{text}}} 1")
        count=row.get("occurrence_count",1)
        try: count=max(1,int(count))
        except (TypeError,ValueError): count=1
        lines.append(f'jason_component_engineering_occurrences{{request_id="{_escape(rid)}"}} {count}')
    for metric,help_text,counts,label in [
      ("jason_component_engineering_lifecycle","Requests by lifecycle.",lifecycle,"lifecycle"),
      ("jason_component_engineering_active_kind","Active requests by request kind.",kind,"kind"),
      ("jason_component_engineering_active_risk","Active requests by risk class.",risk,"risk"),
    ]:
        lines += [f"# HELP {metric} {help_text}",f"# TYPE {metric} gauge"]
        for key,value in sorted(counts.items()): lines.append(f'{metric}{{{label}="{_escape(key)}"}} {value}')
    lines += [
      "# HELP jason_component_engineering_exporter_build_info Jason Component Engineering exporter metadata.",
      "# TYPE jason_component_engineering_exporter_build_info gauge",
      'jason_component_engineering_exporter_build_info{version="2"} 1',
    ]
    return "\n".join(lines)+"\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa:N802
        if self.path not in ("/","/metrics"):
            self.send_response(404); self.end_headers(); return
        payload=render_metrics().encode()
        self.send_response(200); self.send_header("Content-Type","text/plain; version=0.0.4; charset=utf-8"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def log_message(self,format,*args): return


if __name__=="__main__": HTTPServer((HOST,PORT),Handler).serve_forever()
