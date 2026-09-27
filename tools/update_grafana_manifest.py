#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

REQUIRED_METRICS=[
 {"id":"usage-attribution-up","query":"up{job=\"jason-usage-attribution\"} == 1"},
 {"id":"openai-usage-source","query":"jason_openai_org_usage_source_available == 1"},
 {"id":"openai-cost-source","query":"jason_openai_org_cost_source_available == 1"},
 {"id":"openai-cost-24h","query":"jason_openai_org_cost_usd_24h"},
 {"id":"openai-cost-7d","query":"jason_openai_org_cost_usd_7d"},
 {"id":"openai-cost-mtd","query":"jason_openai_org_cost_usd_mtd"}
]

def digest(path:Path)->str:
 h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1]); p.add_argument('--output',type=Path)
 a=p.parse_args(); root=a.repo_root.resolve(); out=a.output or root/'config/observability/grafana-dashboard-manifest.json'
 base=root/'infrastructure/showcase/grafana/dashboards'; dashboards=[]
 for path in sorted(base.glob('*.json')):
  data=json.loads(path.read_text(encoding='utf-8'))
  if not data.get('uid') or not data.get('title'): raise SystemExit(f'missing uid/title: {path}')
  dashboards.append({'uid':data['uid'],'title':data['title'],'path':str(path.relative_to(root)),'sha256':digest(path)})
 payload={'schema_version':'1.0','provider':{'name':'Jason Command Center','folder':'Jason'},'required_datasources':[{'uid':'jason-prometheus','type':'prometheus'}],'dashboards':dashboards,'required_metrics':REQUIRED_METRICS}
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print(f'GRAFANA_MANIFEST_DASHBOARDS={len(dashboards)}'); print(f'OUTPUT={out}')
 return 0
if __name__=='__main__': raise SystemExit(main())
