from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from tools.ccc_runner import CCCConfig, CCCRunner, CheckResult, _matches


def config(tmp_path: Path, *, cadence_days: int = 30) -> CCCConfig:
    path=tmp_path/'ccc.json'
    path.write_text(json.dumps({
        'enabled': True,
        'cadence_days': cadence_days,
        'repository_root': str(tmp_path/'repo'),
        'evidence_root': str(tmp_path/'evidence'),
        'recovery_root': str(tmp_path/'recovery'),
        'state_root': str(tmp_path/'state'),
        'material_path_prefixes': ['implementation/','docs/foundation/'],
        'checker_sensitive_prefixes': ['tools/ccc_'],
        'runtime_sensitive_prefixes': ['implementation/runtime_service/'],
        'provider_canaries': [],
    }),encoding='utf-8')
    return CCCConfig.load(path)


def test_configurable_cadence(tmp_path: Path) -> None:
    loaded=config(tmp_path,cadence_days=45)
    assert loaded.cadence_days == 45
    assert loaded.ccc_principal_id == 'jason-ccc-worker'


def test_prefix_match_is_deterministic() -> None:
    assert _matches('implementation/runtime_service/a.py',('implementation/',))
    assert _matches('docs/foundation/J-002-Constitution.md',('docs/foundation/J-002-Constitution.md',))
    assert not _matches('SUPPORT.md',('implementation/',))


def test_overall_status_fails_closed() -> None:
    assert CCCRunner._overall_status([CheckResult('a','PASS','ok')]) == 'PASS'
    assert CCCRunner._overall_status([CheckResult('a','PASS','ok'),CheckResult('b','NOT_PROVEN','missing')]) == 'NOT_PROVEN'
    assert CCCRunner._overall_status([CheckResult('a','NOT_PROVEN','missing'),CheckResult('b','FAIL','bad')]) == 'FAIL'


def test_schedule_due_uses_last_compliant_age(tmp_path: Path) -> None:
    cfg=config(tmp_path,cadence_days=30)
    now=datetime(2026,9,27,12,0,tzinfo=timezone.utc)
    cfg.evidence_root.mkdir(parents=True)
    (cfg.evidence_root/'last-known-compliant.json').write_text(json.dumps({
        'promoted_at': (now-timedelta(days=29)).isoformat(),
        'source_revision': 'a'*40,
    }),encoding='utf-8')
    runner=CCCRunner(cfg,checker_revision='b'*40,now=lambda:now)
    assert runner._schedule_due() is False
    (cfg.evidence_root/'last-known-compliant.json').write_text(json.dumps({
        'promoted_at': (now-timedelta(days=30,seconds=1)).isoformat(),
        'source_revision': 'a'*40,
    }),encoding='utf-8')
    assert runner._schedule_due() is True


def test_material_review_must_match_exact_revision(tmp_path: Path) -> None:
    cfg=config(tmp_path)
    cfg.state_root.mkdir(parents=True)
    runner=CCCRunner(cfg,checker_revision='b'*40)
    (cfg.state_root/'material-review.json').write_text(json.dumps({
        'status':'approved','source_revision':'a'*40,'recorded_by':'person-al'
    }),encoding='utf-8')
    assert runner._material_review('a'*40) is not None
    assert runner._material_review('c'*40) is None
