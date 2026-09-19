#!/usr/bin/env python3
from __future__ import annotations
import json,os
from collections import Counter
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
ROOT=Path(os.environ.get('JASON_COMPLETION_GAPS_PATH','/var/lib/jason/openclaw/completion-gaps'))
HOST=os.environ.get('JASON_COMPLETION_GAP_EXPORTER_HOST','0.0.0.0'); PORT=int(os.environ.get('JASON_COMPLETION_GAP_EXPORTER_PORT','9474'))
def e(v): return str(v).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
def load():
 if not ROOT.exists(): return []
 out=[]
 for p in sorted(ROOT.glob('*.json')):
  try:
   x=json.loads(p.read_text());
   if isinstance(x,dict): out.append(x)
  except Exception: pass
 return out
def render_metrics():
 rows=load(); active=[x for x in rows if x.get('lifecycle') not in {'resolved','deferred'}]; by_class=Counter(str(x.get('gap_class','unknown')) for x in active); by_route=Counter(str(x.get('route_target','unknown')) for x in active); by_life=Counter(str(x.get('lifecycle','unknown')) for x in rows)
 lines=['# HELP jason_completion_gaps_total Durable completion gaps.','# TYPE jason_completion_gaps_total gauge',f'jason_completion_gaps_total {len(rows)}','# HELP jason_completion_gaps_active Active completion gaps.','# TYPE jason_completion_gaps_active gauge',f'jason_completion_gaps_active {len(active)}','# HELP jason_completion_gap_info Secret-safe completion-gap metadata.','# TYPE jason_completion_gap_info gauge']
 for x in rows:
  labels={k:str(x.get(k,'')) for k in ('gap_id','problem_key','gap_class','title','route_target','lifecycle')}; lines.append('jason_completion_gap_info{'+','.join(f'{k}="{e(v)}"' for k,v in labels.items())+'} 1'); lines.append(f'jason_completion_gap_occurrences{{gap_id="{e(x.get("gap_id",""))}"}} {max(1,int(x.get("occurrence_count",1) or 1))}')
 for metric,label,c in [('jason_completion_gaps_by_class','gap_class',by_class),('jason_completion_gaps_by_route','route_target',by_route),('jason_completion_gaps_by_lifecycle','lifecycle',by_life)]:
  for k,v in sorted(c.items()): lines.append(f'{metric}{{{label}="{e(k)}"}} {v}')
 lines += ['# HELP jason_completion_gap_exporter_build_info Completion gap exporter metadata.','# TYPE jason_completion_gap_exporter_build_info gauge','jason_completion_gap_exporter_build_info{version="1"} 1']
 return '\n'.join(lines)+'\n'
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in ('/','/metrics'): self.send_response(404); self.end_headers(); return
  b=render_metrics().encode(); self.send_response(200); self.send_header('Content-Type','text/plain; version=0.0.4; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,format,*args): return
if __name__=='__main__': HTTPServer((HOST,PORT),H).serve_forever()
