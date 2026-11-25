from types import SimpleNamespace
import pytest
from tools.constant_contact_reconcile_once import run_cycle, main
from connectors.constant_contact.import_reconcile import ReconcileCycle


def test_readonly_cycle_requires_independent_worker():
    with pytest.raises(RuntimeError, match="not activated"):
        run_cycle(SimpleNamespace(constant_contact_reconciliation_worker=None))


def test_readonly_cycle_runs_only_bound_worker():
    class Worker:
        def run_once(self, *, max_items):
            assert max_items == 2
            return ReconcileCycle(considered=2, verified=1, pending=1,
                                  blocked=0, reasons=())
    result = run_cycle(SimpleNamespace(constant_contact_reconciliation_worker=Worker()),
                       max_items=2)
    assert result["verified"] == 1
    assert result["pending"] == 1


def test_cli_disabled_by_default_never_composes(monkeypatch, capsys):
    monkeypatch.delenv("JASON_CONSTANT_CONTACT_RECONCILE_PROFILE", raising=False)
    assert main(["--check-only"]) == 0
    assert '"executed": false' in capsys.readouterr().out
    assert main(["--run-once"]) == 2
    assert '"disabled"' in capsys.readouterr().out
