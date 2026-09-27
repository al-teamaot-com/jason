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
