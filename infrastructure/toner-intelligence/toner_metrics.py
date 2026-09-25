from __future__ import annotations
import json, sys
from pathlib import Path

def esc(v): return str(v or '').replace('\\','\\\\').replace('"','\\"').replace('\n',' ')

def render(path):
    data=json.loads(Path(path).read_text()); lines=[]
    age=data.get('collector_age_hours')
    if age is not None:
        lines += ['# HELP jason_kfs_latest_successful_run_age_seconds Age of latest successful KFS collection in seconds.',
                  '# TYPE jason_kfs_latest_successful_run_age_seconds gauge',
                  f'jason_kfs_latest_successful_run_age_seconds {age*3600:.3f}']
    lines += [
        '# HELP jason_toner_current_percent Latest valid KFS toner percentage.',
        '# TYPE jason_toner_current_percent gauge',
        '# HELP jason_toner_seconds_remaining Forecast seconds until toner depletion under the current prototype trend.',
        '# TYPE jason_toner_seconds_remaining gauge',
        '# HELP jason_toner_burn_percent_per_second Forecast toner percentage-point burn per second.',
        '# TYPE jason_toner_burn_percent_per_second gauge',
        '# HELP jason_toner_replacement_events Probable low-to-full cartridge replacement events observed in the analysis window.',
        '# TYPE jason_toner_replacement_events gauge',
        '# HELP jason_toner_missed_successful_runs Number of successful KFS collections since this toner last reported.',
        '# TYPE jason_toner_missed_successful_runs gauge'
    ]
    devices={}
    for i in data['items']:
        labels={k:i.get(k,'') for k in ('customer','device_id','serial','color','part_number','action','confidence','seasonality_status','telemetry_state')}
        ls=','.join(f'{k}="{esc(v)}"' for k,v in labels.items())
        lines.append(f'jason_toner_current_percent{{{ls}}} {i["current_level"]}')
        if i.get('days_remaining') is not None:
            lines.append(f'jason_toner_seconds_remaining{{{ls}}} {i["days_remaining"]*86400:.3f}')
        if i.get('burn_pct_per_day') is not None:
            lines.append(f'jason_toner_burn_percent_per_second{{{ls}}} {i["burn_pct_per_day"]/86400:.12f}')
        lines.append(f'jason_toner_replacement_events{{{ls}}} {i.get("replacement_events",0)}')
        lines.append(f'jason_toner_missed_successful_runs{{{ls}}} {i.get("missed_toner_runs",0)}')
        devices[i['device_id']]=i
    lines += ['# HELP jason_kfs_device_reporting_state One record per KFS device; value is always 1 and device_reporting_state is a label.',
              '# TYPE jason_kfs_device_reporting_state gauge']
    for i in devices.values():
        labels={k:i.get(k,'') for k in ('customer','device_id','serial','device_reporting_state')}
        ls=','.join(f'{k}="{esc(v)}"' for k,v in labels.items())
        lines.append(f'jason_kfs_device_reporting_state{{{ls}}} 1')
    return '\n'.join(lines)+'\n'

if __name__=='__main__': print(render(sys.argv[1] if len(sys.argv)>1 else '/tmp/jason-toner-preview.json'),end='')
