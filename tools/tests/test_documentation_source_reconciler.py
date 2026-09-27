from tools.documentation_source_reconciler import REQUIRED_WORKFLOWS, is_material


def test_material_change_excludes_docs_and_workflow_only_changes():
    assert not is_material(("docs/control/CURRENT.md", ".github/workflows/validate.yml"))
    assert is_material(("tools/example.py", "docs/control/CURRENT.md"))


def test_expected_protected_workflows_are_exact():
    assert REQUIRED_WORKFLOWS == {
        "Validate Jason",
        "SEC-007 Security Regressions",
        "Validate Jason Teams Gateway",
        "Validate Conversation Experience Foundation",
    }


def test_main_does_not_republish_while_generated_pr_is_waiting(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.merge_ready_automation_prs",
        lambda: "waiting",
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.publish_source_if_needed",
        lambda: calls.append("publish"),
    )
    from tools.documentation_source_reconciler import main
    assert main() == 0
    assert calls == []


def test_main_refreshes_conflicting_generated_pr(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.merge_ready_automation_prs",
        lambda: "refresh",
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.publish_source_if_needed",
        lambda: calls.append("publish"),
    )
    from tools.documentation_source_reconciler import main
    assert main() == 0
    assert calls == ["publish"]


def test_main_stops_after_merge_until_next_cycle(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.merge_ready_automation_prs",
        lambda: "merged",
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.publish_source_if_needed",
        lambda: calls.append("publish"),
    )
    from tools.documentation_source_reconciler import main
    assert main() == 0
    assert calls == []
