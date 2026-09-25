from __future__ import annotations
import json, sys
from pathlib import Path

def esc(v): return str(v or '').replace('\\','\\\\').replace('"','\\"').replace('\n',' ')

def render(path):
    data=json.loads(Path(path).read_text())
    lines=['# HELP jason_toner_current_percent Latest KFS toner percentage.','# TYPE jason_toner_current_percent gauge']
    for i in data['items']:
        labels={k:i.get(k,'') for k in ('customer','device_id','serial','color','part_number','action','confidence','seasonality_status')}
        ls=','.join(f'{k}="{esc(v)}"' for k,v in labels.items())
        lines.append(f'jason_toner_current_percent{{{ls}}} {i["current_level"]}')
        if i.get('days_remaining') is not None: lines.append(f'jason_toner_days_remaining{{{ls}}} {i["days_remaining"]:.3f}')
        if i.get('burn_pct_per_day') is not None: lines.append(f'jason_toner_burn_percent_per_day{{{ls}}} {i["burn_pct_per_day"]:.6f}')
        lines.append(f'jason_toner_replacement_events{{{ls}}} {i.get("replacement_events",0)}')
    return '\n'.join(lines)+'\n'

if __name__=='__main__': print(render(sys.argv[1] if len(sys.argv)>1 else '/tmp/jason-toner-preview.json'),end='')
