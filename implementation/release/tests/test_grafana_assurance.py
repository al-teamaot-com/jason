from __future__ import annotations
import hashlib, json
from pathlib import Path
from tools.grafana_assurance import Check, DRIFTED, NOT_PROVEN, PASS, file_checks, overall_status


def write_dashboard(root: Path, *, title: str = 'Test Dashboard') -> tuple[Path, dict]:
    path=root/'infrastructure/showcase/grafana/dashboards/test.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'uid':'test-dashboard','title':title}),encoding='utf-8')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    item={'uid':'test-dashboard','title':'Test Dashboard','path':str(path.relative_to(root)),'sha256':digest}
    return path,item


def test_file_check_passes_exact_manifest(tmp_path: Path) -> None:
    _,item=write_dashboard(tmp_path)
    result=file_checks(tmp_path,{'dashboards':[item]})
    assert len(result)==1 and result[0].status==PASS


def test_file_check_detects_hash_or_identity_drift(tmp_path: Path) -> None:
    path,item=write_dashboard(tmp_path)
    path.write_text(json.dumps({'uid':'test-dashboard','title':'Changed'}),encoding='utf-8')
    result=file_checks(tmp_path,{'dashboards':[item]})
    assert result[0].status==DRIFTED


def test_overall_status_is_fail_closed() -> None:
    assert overall_status([Check('a',PASS,'ok')])==PASS
    assert overall_status([Check('a',NOT_PROVEN,'unknown')])==NOT_PROVEN
    assert overall_status([Check('a',NOT_PROVEN,'unknown'),Check('b',DRIFTED,'bad')])==DRIFTED


def test_grafana_assurance_exporter_port_is_dedicated() -> None:
    root = Path(__file__).resolve().parents[3]
    service = (root / 'infrastructure/showcase/systemd/jason-grafana-assurance-exporter.service').read_text(encoding='utf-8')
    target = json.loads((root / 'infrastructure/showcase/prometheus/file_sd/jason-grafana-assurance.json').read_text(encoding='utf-8'))
    assert 'JASON_GRAFANA_ASSURANCE_PORT=9474' in service
    assert target[0]['targets'] == ['host.docker.internal:9474']


def test_observability_installer_deploys_from_exact_release_and_restores_pointer_on_failure() -> None:
    root = Path(__file__).resolve().parents[3]
    installer = (root / 'tools/install_observability_assurance.sh').read_text(encoding='utf-8')
    assert 'JASON_REPO_ROOT="$RELEASE_DIR"' in installer
    assert '/usr/bin/bash "$RELEASE_DIR/infrastructure/showcase/deploy_usage_dashboard.sh"' in installer
    assert 'ln -sfn "$OLD_CURRENT" "$CURRENT_LINK"' in installer
