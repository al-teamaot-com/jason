from __future__ import annotations
import csv, io, json, subprocess, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from toner_intelligence import Reading, detect_replacements, forecast

SQL = r"""
COPY (
  SELECT c.reading_at, c.device_id, c.serial_number, c.equipment_id,
         coalesce(nullif(c.customer_id,''),nullif(d.customer_id,''),g.customer_id) customer_id,
         coalesce(nullif(c.customer_name,''),nullif(d.customer_name,''),nullif(g.customer_name,''),g.group_name,'') customer_name,
         c.consumable_type, c.color, c.level_percent, c.part_number
  FROM public.kfs_consumable_readings c
  LEFT JOIN public.kfs_devices d ON d.device_id=c.device_id
  LEFT JOIN public.kfs_groups g ON g.group_id=c.group_id
  WHERE c.consumable_type='toner' AND reading_at >= now() - interval '45 days'
  ORDER BY customer_name, device_id, color, reading_at
) TO STDOUT WITH CSV HEADER
"""


def load_rows():
    cmd=['docker','exec','jason-kfs-postgres','psql','-U','kfs_collector','-d','kfs_collector','-c',SQL]
    result=subprocess.run(cmd,check=True,capture_output=True,text=True)
    return list(csv.DictReader(io.StringIO(result.stdout)))


def main(path: str):
    grouped=defaultdict(list); meta={}
    for row in load_rows():
        raw=row.get('level_percent','').strip()
        if not raw or not raw.lstrip('-').isdigit():
            continue
        level=int(raw)
        if level < 0 or level > 100:
            continue
        key=(row['device_id'],row['color'])
        grouped[key].append(Reading(datetime.fromisoformat(row['reading_at'].replace('Z','+00:00')),level))
        meta[key]=row
    items=[]
    for key, readings in grouped.items():
        m=meta[key]; f=forecast(readings,1.0); replacements=detect_replacements(readings)
        action=f.action
        reason=f.reason
        if action in {'ship_today','ship_soon'} and (not m['customer_name'].strip() or not m['part_number'].strip()):
            action='needs_review'
            reason='missing customer identity or toner part number'
        items.append({
            'customer':m['customer_name'],'device_id':m['device_id'],'serial':m['serial_number'],
            'equipment_id':m['equipment_id'],'color':m['color'],'part_number':m['part_number'],
            'current_level':f.current_level,'burn_pct_per_day':f.burn_pct_per_day,
            'days_remaining':f.days_remaining,'action':action,'confidence':f.confidence,
            'reason':reason,'seasonal_factor':1.0,'seasonality_status':'insufficient_history',
            'replacement_events':len(replacements),'coverage_status':'not_evaluated'
        })
    items.sort(key=lambda x:({'ship_today':0,'ship_soon':1,'needs_review':2,'watch':3}.get(x['action'],9), x['days_remaining'] if x['days_remaining'] is not None else 9999))
    Path(path).write_text(json.dumps({'generated_at':datetime.now().astimezone().isoformat(),'items':items},indent=2))
    print(json.dumps({'items':len(items),'ship_today':sum(i['action']=='ship_today' for i in items),'ship_soon':sum(i['action']=='ship_soon' for i in items),'needs_review':sum(i['action']=='needs_review' for i in items),'watch':sum(i['action']=='watch' for i in items),'replacement_events':sum(i['replacement_events'] for i in items)},indent=2))

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else '/tmp/jason-toner-preview.json')
