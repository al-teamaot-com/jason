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


@pytest.fixture
def matrix_fixture(tmp_path, monkeypatch):
    """Exercise the actual receipt gate with synthetic JUnit, never a provider."""
    from types import SimpleNamespace
    import json
    from tools import legacy_json_preprod_matrix as matrix

    root = tmp_path / "source"
    root.mkdir()
    modules = set(matrix.SHARED_RECOVERY + matrix.BOUNDARY_TESTS)
    for paths in matrix.CASE_TESTS.values():
        modules.update(paths)
    for name in modules:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
    entries = [
        {"id": name, "json_fingerprint": "a" * 64}
        for name in sorted(matrix.CASE_TESTS)
    ]
    monkeypatch.setattr(matrix, "ROOT", root)
    monkeypatch.setattr(matrix, "build", lambda: {
        "entries": entries, "fully_accepted_migrations": 0,
    })
    output = root / "tmp/json-preprod-parity-recovery"
    output.mkdir(parents=True)
    latest = output / "matrix-results.json"
    scenario = {"omit": None, "skip": None, "unexpected": False,
                "missing_junit": False, "timeout": False}

    def fake_run(cmd, **kwargs):
        junit = Path(cmd[cmd.index("--junitxml") + 1])
        pending = json.loads(latest.read_text())
        assert pending["status"] == "isolated_synthetic_matrix_pending"
        assert pending["run_id"] == junit.parent.name
        assert not junit.exists()
        if scenario["timeout"]:
            raise matrix.subprocess.TimeoutExpired(cmd, 180)
        if not scenario["missing_junit"]:
            xml = ET.Element("testsuites")
            suite = ET.SubElement(xml, "testsuite")
            for name in sorted(modules):
                if name == scenario["omit"]:
                    continue
                tc = ET.SubElement(suite, "testcase", file=name, name="test_case")
                if name == scenario["skip"]:
                    ET.SubElement(tc, "skipped")
            for entry in entries:
                ET.SubElement(
                    suite, "testcase",
                    file="tests/test_legacy_json_preprod_recovery_all19.py",
                    name="test_exact_candidate_draft_reopen_no_replay_or_mutation["+
                         entry["id"]+"]",
                )
            if scenario["unexpected"]:
                ET.SubElement(suite, "testcase", file="tests/unexpected.py",
                              name="test_unexpected")
            ET.ElementTree(xml).write(junit, encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="synthetic fixture")

    monkeypatch.setattr(matrix.subprocess, "run", fake_run)
    return matrix, root, latest, scenario


def test_matrix_requires_every_module_and_fresh_receipt(matrix_fixture):
    import json
    matrix, root, latest, _ = matrix_fixture
    first = matrix.run(root=root)
    assert first["status"] == "isolated_synthetic_matrix_pass"
    assert all(value == "pass" for value in
               first["required_test_module_results"].values())
    second = matrix.run(root=root)
    assert second["status"] == "isolated_synthetic_matrix_pass"
    assert second["run_id"] != first["run_id"]
    assert json.loads(latest.read_text()) == second
    assert (latest.parent / first["run_id"] / "pytest-matrix.xml").is_file()
    assert (latest.parent / second["run_id"] / "pytest-matrix.xml").is_file()


@pytest.mark.parametrize("key,module", [
    ("skip", "implementation/runtime_service/tests/test_json_backupiq_classifier.py"),
    ("skip", "tests/test_legacy_json_preprod_boundary.py"),
    ("omit", "tests/test_json_playbook_isolated_trace.py"),
    ("omit", "implementation/runtime_service/tests/test_json_windows_time_sweep.py"),
])
def test_matrix_rejects_incomplete_module_coverage(matrix_fixture, key, module):
    matrix, root, _, scenario = matrix_fixture
    scenario[key] = module
    result = matrix.run(root=root)
    assert result["status"] == "isolated_synthetic_matrix_failed"
    assert result["required_test_module_results"][Path(module).stem] == "fail_or_missing"


def test_matrix_rejects_unexpected_test_module(matrix_fixture):
    matrix, root, _, scenario = matrix_fixture
    scenario["unexpected"] = True
    result = matrix.run(root=root)
    assert result["status"] == "isolated_synthetic_matrix_failed"
    assert result["unexpected_test_modules"] == ["unexpected"]


@pytest.mark.parametrize("failure", ["missing_junit", "timeout"])
def test_matrix_cannot_reuse_prior_success_after_failed_attempt(matrix_fixture, failure):
    import json
    matrix, root, latest, scenario = matrix_fixture
    first = matrix.run(root=root)
    assert first["status"] == "isolated_synthetic_matrix_pass"
    scenario[failure] = True
    expected = (ValueError if failure == "missing_junit" else
                matrix.subprocess.TimeoutExpired)
    with pytest.raises(expected):
        matrix.run(root=root)
    receipt = json.loads(latest.read_text())
    assert receipt["status"] == "isolated_synthetic_matrix_failed"
    assert receipt["run_id"] != first["run_id"]
    assert (latest.parent / first["run_id"] / "pytest-matrix.xml").exists()
    assert not (latest.parent / receipt["run_id"] / "pytest-matrix.xml").exists()
