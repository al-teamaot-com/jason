#!/usr/bin/env python3
from __future__ import annotations
import json,os
from collections import Counter
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
CATALOG=Path(os.environ.get('JASON_COMMUNICATION_TEMPLATE_CATALOG','/var/lib/jason/communications/approved-templates.json'))
REQUESTS=Path(os.environ.get('JASON_COMMUNICATION_TEMPLATE_REQUESTS_PATH','/var/lib/jason/communications/template-requests'))
HOST=os.environ.get('JASON_COMMUNICATION_TEMPLATE_EXPORTER_HOST','0.0.0.0'); PORT=int(os.environ.get('JASON_COMMUNICATION_TEMPLATE_EXPORTER_PORT','9473'))
def e(v): return str(v).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
def load_catalog():
 if not CATALOG.exists(): return []
 try: return [x for x in json.loads(CATALOG.read_text()).get('templates',[]) if isinstance(x,dict)]
 except Exception: return []
def load_requests():
 if not REQUESTS.exists(): return []
 out=[]
 for p in sorted(REQUESTS.glob('*.json')):
  try:
   x=json.loads(p.read_text());
   if isinstance(x,dict): out.append(x)
  except Exception: pass
 return out
def render_metrics():
 templates=load_catalog(); approved=[x for x in templates if x.get('approved') is True]; reqs=load_requests(); active=[x for x in reqs if str(x.get('lifecycle','')) not in {'published','resolved'}]
 by_audience=Counter(str(x.get('audience','unknown')) for x in approved); by_lifecycle=Counter(str(x.get('lifecycle','unknown')) for x in reqs)
 lines=['# HELP jason_communication_templates_approved Approved templates in Jason catalog.','# TYPE jason_communication_templates_approved gauge',f'jason_communication_templates_approved {len(approved)}','# HELP jason_communication_template_requests Durable template-gap requests.','# TYPE jason_communication_template_requests gauge',f'jason_communication_template_requests {len(reqs)}','# HELP jason_communication_template_active_requests Active template-gap requests.','# TYPE jason_communication_template_active_requests gauge',f'jason_communication_template_active_requests {len(active)}','# HELP jason_communication_template_request_info Secret-safe request metadata.','# TYPE jason_communication_template_request_info gauge']
 for x in reqs:
  labels={k:str(x.get(k,'')) for k in ('request_id','purpose_key','audience','lifecycle','proposed_name','proposed_subject')}; lines.append('jason_communication_template_request_info{'+','.join(f'{k}="{e(v)}"' for k,v in labels.items())+'} 1'); lines.append(f'jason_communication_template_request_occurrences{{request_id="{e(x.get("request_id",""))}"}} {max(1,int(x.get("occurrence_count",1) or 1))}')
 for k,v in sorted(by_audience.items()): lines.append(f'jason_communication_templates_by_audience{{audience="{e(k)}"}} {v}')
 for k,v in sorted(by_lifecycle.items()): lines.append(f'jason_communication_template_requests_by_lifecycle{{lifecycle="{e(k)}"}} {v}')
 lines += ['# HELP jason_communication_template_exporter_build_info Jason communication-template exporter metadata.','# TYPE jason_communication_template_exporter_build_info gauge','jason_communication_template_exporter_build_info{version="1"} 1']
 return '\n'.join(lines)+'\n'
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in ('/','/metrics'): self.send_response(404); self.end_headers(); return
  b=render_metrics().encode(); self.send_response(200); self.send_header('Content-Type','text/plain; version=0.0.4; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,format,*args): return
if __name__=='__main__': HTTPServer((HOST,PORT),H).serve_forever()
