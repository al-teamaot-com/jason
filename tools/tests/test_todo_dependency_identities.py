from tools.todo_release_bridge import explicit_release_dependencies


def test_exact_release_ids_are_parsed_deduplicated():
    source = "- Governing release dependencies: release-1234567890abcdef, release-1234567890abcdef, release-abcdef1234567890"
    assert explicit_release_dependencies(source) == ["release-1234567890abcdef", "release-abcdef1234567890"]


def test_free_text_issue_numbers_never_infer_authority():
    assert explicit_release_dependencies("Depends on SUPPORT-CAP-006 through -011 and issue #1078") == []
    assert explicit_release_dependencies("- Governing release dependencies: issue-1078") == []
    assert explicit_release_dependencies("- Governing release dependencies: release-bad") == []
