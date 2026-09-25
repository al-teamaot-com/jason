from __future__ import annotations
import csv, io, json, subprocess, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from toner_intelligence import Reading, apply_safety_gates, classify_telemetry, detect_replacements, forecast

READINGS_SQL = r"""
COPY (
  SELECT c.reading_at, c.run_id, c.device_id, c.serial_number, c.equipment_id,
         coalesce(nullif(c.customer_id,''),nullif(d.customer_id,''),g.customer_id) customer_id,
         coalesce(nullif(c.customer_name,''),nullif(d.customer_name,''),nullif(g.customer_name,''),g.group_name,'') customer_name,
         c.consumable_type, c.color, c.level_percent, c.part_number,
         d.last_seen_at AS device_last_seen_at
  FROM public.kfs_consumable_readings c
  LEFT JOIN public.kfs_devices d ON d.device_id=c.device_id
  LEFT JOIN public.kfs_groups g ON g.group_id=c.group_id
  WHERE c.consumable_type='toner' AND c.reading_at >= now() - interval '45 days'
  ORDER BY customer_name, device_id, color, reading_at
) TO STDOUT WITH CSV HEADER
"""
RUNS_SQL = r"""
COPY (
  SELECT id, started_at FROM public.kfs_runs
  WHERE status='ok' ORDER BY started_at
) TO STDOUT WITH CSV HEADER
"""


def query(sql: str):
    cmd=['docker','exec','jason-kfs-postgres','psql','-U','kfs_collector','-d','kfs_collector','-c',sql]
    result=subprocess.run(cmd,check=True,capture_output=True,text=True)
    return list(csv.DictReader(io.StringIO(result.stdout)))


def dt(value: str) -> datetime | None:
    value=(value or '').strip()
    return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None


def missed_runs(run_times: list[datetime], observed_at: datetime | None) -> int:
    if observed_at is None:
        return len(run_times)
    return sum(1 for run_at in run_times if run_at > observed_at)


def main(path: str):
    now=datetime.now(timezone.utc)
    run_rows=query(RUNS_SQL)
    run_times=[dt(r['started_at']) for r in run_rows if dt(r['started_at'])]
    latest_run=max(run_times) if run_times else None
    collector_age_hours=((now-latest_run).total_seconds()/3600) if latest_run else None
    collector_current=collector_age_hours is not None and collector_age_hours <= 9

    grouped=defaultdict(list); meta={}
    for row in query(READINGS_SQL):
        raw=row.get('level_percent','').strip()
        if not raw or not raw.lstrip('-').isdigit():
            continue
        level=int(raw)
        if level < 0 or level > 100:
            continue
        key=(row['device_id'],row['color'])
        grouped[key].append(Reading(dt(row['reading_at']),level))
        meta[key]=row

    items=[]
    for key, readings in grouped.items():
        m=meta[key]; f=forecast(readings,1.0); replacements=detect_replacements(readings)
        toner_seen=readings[-1].at
        device_seen=dt(m.get('device_last_seen_at'))
        missed_device=missed_runs(run_times,device_seen)
        missed_toner=missed_runs(run_times,toner_seen)
        device_age_days=((now-device_seen).total_seconds()/86400) if device_seen else 9999.0
        telemetry_state, telemetry_reason=classify_telemetry(missed_device,missed_toner,device_age_days)
        device_state=classify_telemetry(missed_device,0,device_age_days)[0]
        if not collector_current:
            telemetry_state='collection_stale'
            telemetry_reason='latest successful KFS collection is older than 9 hours'
            device_state='collection_stale'

        action, reason=apply_safety_gates(f.action,f.reason,telemetry_state,telemetry_reason,
                                          m['customer_name'],m['part_number'])

        items.append({
            'customer':m['customer_name'],'device_id':m['device_id'],'serial':m['serial_number'],
            'equipment_id':m['equipment_id'],'color':m['color'],'part_number':m['part_number'],
            'current_level':f.current_level,'burn_pct_per_day':f.burn_pct_per_day,
            'days_remaining':f.days_remaining,'action':action,'confidence':f.confidence,'reason':reason,
            'telemetry_state':telemetry_state,'device_reporting_state':device_state,
            'device_last_seen_at':device_seen.isoformat() if device_seen else None,
            'toner_last_seen_at':toner_seen.isoformat(),'missed_device_runs':missed_device,
            'missed_toner_runs':missed_toner,'seasonal_factor':1.0,
            'seasonality_status':'insufficient_history','replacement_events':len(replacements),
            'coverage_status':'not_evaluated'
        })
    items.sort(key=lambda x:({'ship_today':0,'ship_soon':1,'needs_review':2,'watch':3}.get(x['action'],9), x['days_remaining'] if x['days_remaining'] is not None else 9999))
    summary={
        'items':len(items),'ship_today':sum(i['action']=='ship_today' for i in items),
        'ship_soon':sum(i['action']=='ship_soon' for i in items),
        'needs_review':sum(i['action']=='needs_review' for i in items),
        'watch':sum(i['action']=='watch' for i in items),
        'replacement_events':sum(i['replacement_events'] for i in items),
        'devices_not_current':len({i['device_id'] for i in items if i['device_reporting_state']!='current'}),
        'toners_not_current':sum(i['telemetry_state']!='current' for i in items)
    }
    payload={'generated_at':now.astimezone().isoformat(),'latest_successful_run_at':latest_run.isoformat() if latest_run else None,
             'collector_age_hours':collector_age_hours,'collector_current':collector_current,'summary':summary,'items':items}
    Path(path).write_text(json.dumps(payload,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else '/tmp/jason-toner-preview.json')
