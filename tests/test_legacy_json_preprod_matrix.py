"""Source matrix coverage must be complete without live provider access."""
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from tools.legacy_json_acceptance_ledger import ROOT, build
from tools.legacy_json_preprod_matrix import (
    CASE_TESTS, SHARED_RECOVERY, BOUNDARY_TESTS,
    _counts, run,
)


def test_all_19_source_candidates_have_existing_replay_suites():
    cases={x["id"] for x in build()["entries"]}
    assert set(CASE_TESTS)==cases
    assert len(cases)==19
    assert all(paths for paths in CASE_TESTS.values())
    paths={p for group in CASE_TESTS.values() for p in group}
    paths.update(SHARED_RECOVERY)
    paths.update(BOUNDARY_TESTS)
    assert all((ROOT/p).is_file() for p in paths)
    assert all(str(p).startswith(("tests/","implementation/runtime_service/tests/"))
               for p in paths)


def test_matrix_rejects_any_other_or_production_execution_root(tmp_path):
    with pytest.raises(ValueError,match="SOURCE_ROOT_CHANGED"):
        run(root=tmp_path)


def test_junit_auditing_counts_real_runs_without_mistaking_skips_for_pass(tmp_path):
    p=tmp_path/"test.xml"
    p.write_text('''<testsuites><testsuite>
      <testcase classname="tests.a" name="test_ok" file="tests/a.py"/>
      <testcase classname="tests.a" name="test_failed" file="tests/a.py">
        <failure>failed</failure></testcase>
      <testcase classname="tests.b" name="test_skip" file="tests/b.py">
        <skipped>skipped</skipped></testcase>
      </testsuite></testsuites>''')
    counts,totals=_counts(p)
    assert totals=={"passed":1,"failed":1,"errors":0,"skipped":1,"executed":3}
    assert counts["a"]["failed"]==1
    assert counts["b"]["skipped"]==1
