from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_host_installer_copies_reader_and_checks_presence():
    source = (ROOT / 'install_support_repair_host_worker.py').read_text()
    assert "operational_acceptance_reader = repo / 'tools' / 'operational_acceptance_reader.py'" in source
    assert "if not operational_acceptance_reader.is_file():" in source
    assert "_copy(operational_acceptance_reader, install_root / 'operational_acceptance_reader.py', 0o700)" in source


def test_host_reconciliation_checks_reader_matches_source():
    source = (ROOT / 'reconcile_production_host_services.sh').read_text()
    assert '  operational_acceptance_reader.py \\' in source
