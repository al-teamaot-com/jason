import importlib.util
import datetime
from pathlib import Path
import pytest

p=Path(__file__).resolve().parents[1]/'root_revalidate_release_breaker.py'
s=importlib.util.spec_from_file_location('root_revalidate_release_breaker',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
REV='a'*40

def good():
    control={'schema_version':'1.0','circuit_breaker':{'state':'open'},'last_known_good':{'manifest':{'revision':REV}}}
    drift={'schema_version':'1.0','status':'pass','problems':[], 'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    return control,drift

def test_valid_evidence():
    m.validate(*good(),REV)

def test_fail_closed_for_drift_open_and_lkg():
    a,b=good();b['status']='drift_detected'
    with pytest.raises(ValueError):m.validate(a,b,REV)
    a,b=good();a['circuit_breaker']['state']='closed'
    with pytest.raises(ValueError):m.validate(a,b,REV)
    a,b=good();a['last_known_good']['manifest']['revision']='b'*40
    with pytest.raises(ValueError):m.validate(a,b,REV)

def test_stale_and_future_evidence_rejected():
    a,b=good();b['observed_at']='2020-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):m.validate(a,b,REV)
    a,b=good();b['observed_at']='2099-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):m.validate(a,b,REV)
