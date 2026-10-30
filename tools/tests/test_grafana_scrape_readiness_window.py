"""Keep actual assurance mandatory while covering the declared 120s scrape."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]


def test_real_grafana_check_has_bounded_window_covering_slowest_required_scrape():
    script=(ROOT/'tools/reconcile_production_host_services.sh').read_text()
    block=script.split('step_start post_exporter_grafana_assurance',1)[1].split('step_pass post_exporter_grafana_assurance',1)[0]
    config=(ROOT/'infrastructure/showcase/prometheus/prometheus.yml').read_text()
    assert 'scrape_interval: 2m' in config
    assert 'GRAFANA_REVALIDATION_DEADLINE=$((SECONDS + 150))' in block
    assert 'remaining=$((GRAFANA_REVALIDATION_DEADLINE - SECONDS))' in block
    assert 'check_timeout=$((remaining < 20 ? remaining : 20))' in block
    assert 'systemctl start jason-grafana-assurance.service' in block
    assert '-p Result --value)' in block
    assert '"success"' in block
    assert 'if [ "$GRAFANA_REVALIDATION_PASS" -ne 1 ]' in block and 'exit 9' in block
    assert 'reset-failed' not in block and 'mask ' not in block
    worker=(ROOT/'tools/release_host_reconcile_worker.py').read_text()
    budget=int(re.search(r'HOST_RECONCILE_TIMEOUT_SECONDS = (\d+)',worker).group(1))
    assert budget >= 360
