from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]

def test_manifest_matches_all_repository_dashboard_files() -> None:
    manifest=json.loads((ROOT/'config/observability/grafana-dashboard-manifest.json').read_text(encoding='utf-8'))
    entries={x['path']:x for x in manifest['dashboards']}
    files=sorted((ROOT/'infrastructure/showcase/grafana/dashboards').glob('*.json'))
    assert len(entries)==len(files)
    for path in files:
        rel=str(path.relative_to(ROOT)); assert rel in entries
        payload=json.loads(path.read_text(encoding='utf-8')); entry=entries[rel]
        assert entry['uid']==payload['uid']; assert entry['title']==payload['title']
        assert entry['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()


def test_openai_cost_dependency_contract_is_declared() -> None:
    manifest=json.loads((ROOT/'config/observability/grafana-dashboard-manifest.json').read_text(encoding='utf-8'))
    queries={x['query'] for x in manifest['required_metrics']}
    assert 'jason_openai_org_usage_source_available == 1' in queries
    assert 'jason_openai_org_cost_source_available == 1' in queries
    assert 'jason_openai_org_cost_usd_24h' in queries
    assert 'jason_openai_org_cost_usd_7d' in queries
    assert 'jason_openai_org_cost_usd_mtd' in queries
