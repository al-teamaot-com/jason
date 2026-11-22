"""Independently protected PMv4 health is inside catalog's native rollback gate."""
from __future__ import annotations
from types import SimpleNamespace
import pytest

from tools import catalog_scoped_promotion_root as root
from tools import catalog_scoped_promotion_host as host


def isolated_host(monkeypatch):
    native={'jason-pmv4-shadow-gateway':{'id':'no-change'}}
    monkeypatch.setattr(host.NativeCatalogHost,'protected_container_snapshot',
                        lambda self:dict(native))
    # Native's original protected-container verifier uses self.snapshot().
    obj=root.CatalogPMv4ProtectedHost.__new__(root.CatalogPMv4ProtectedHost)
    obj._independent_pmv4_before=None
    return obj,native


def test_independent_pmv4_snapshot_accepts_unchanged_runtime(monkeypatch):
    obj,native=isolated_host(monkeypatch)
    current={'containers':{'jason-pmv4-ticket-core':('id1','image1','start1')},
             'runbook':{'MainPID':'42','ActiveState':'active'},
             'registry':(0,0)}
    monkeypatch.setattr(obj,'_independent_pmv4_readback',lambda:current)
    before=obj.protected_container_snapshot()
    assert before==native
    assert obj._independent_pmv4_before==current
    obj.verify_unchanged_protected_containers(before)


@pytest.mark.parametrize('field,changed',[
    ('containers',{'jason-pmv4-ticket-core':('other','image1','start1')}),
    ('runbook',{'MainPID':'43','ActiveState':'active'}),
    ('registry',(1,1)),
])
def test_independent_regression_triggers_native_rollback_exception(monkeypatch,field,changed):
    obj,native=isolated_host(monkeypatch)
    current={'containers':{'jason-pmv4-ticket-core':('id1','image1','start1')},
             'runbook':{'MainPID':'42','ActiveState':'active'},
             'registry':(0,0)}
    before=obj.protected_container_snapshot() if False else native
    obj._independent_pmv4_before=current.copy()
    candidate=current.copy()
    candidate[field]=changed
    monkeypatch.setattr(obj,'_independent_pmv4_readback',lambda:candidate)
    with pytest.raises(PermissionError,match='INDEPENDENT_PMV4_REGRESSION_ROLLBACK_REQUIRED'):
        obj.verify_unchanged_protected_containers(before)


def test_native_release_calls_independent_guard_before_final_success():
    # This call is within the existing paired-rollback try block.
    import inspect
    from tools import catalog_scoped_promotion
    src=inspect.getsource(catalog_scoped_promotion.promote_scoped_catalog_pair)
    index_verification=src.index('host.verify_unchanged_protected_containers(before)',src.index('host.promote_exact("jason-mcp-pilot"'))
    index_record=src.index('host.record_outcome(offer,"production_pair_verified")')
    index_rollback=src.index('host.rollback_both(offer)')
    assert index_verification<index_record<index_rollback
    assert root.CatalogPMv4ProtectedHost.verify_unchanged_protected_containers is not host.NativeCatalogHost.verify_unchanged_protected_containers


def test_independent_checks_do_not_mutate_ticket_or_runbook_services():
    import inspect
    src=inspect.getsource(root.CatalogPMv4ProtectedHost)
    assert "systemctl','show" in src
    assert "['docker','inspect" in src
    for command in ("docker','stop","docker','run","systemctl','restart","sqlite3.connect(uri,uri=False"):
        assert command not in src
    assert "sqlite3.connect(uri,uri=True,timeout=5)" in src
