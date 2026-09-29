from tools.documentation_source_reconciler import is_material


def test_material_change_excludes_docs_and_workflow_only_changes():
    assert not is_material(("docs/control/CURRENT.md", ".github/workflows/validate.yml"))
    assert is_material(("tools/example.py", "docs/control/CURRENT.md"))


def test_complete_main_history_unshallows_before_ancestry(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        if args[-1] == "--is-shallow-repository":
            return "true"
        return ""

    monkeypatch.setattr("tools.documentation_source_reconciler.run", fake_run)
    from tools.documentation_source_reconciler import ensure_complete_main_history

    ensure_complete_main_history()
    assert any(
        "--unshallow" in call
        and call[-2:] == ("origin", "main")
        for call in calls
    )


def test_changed_paths_does_not_re_shallow_repository(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.ensure_revision",
        lambda revision: calls.append(("ensure", revision)),
    )

    def fake_run(*args, **kwargs):
        calls.append(args)
        return "tools/a.py\ndocs/b.md"

    monkeypatch.setattr("tools.documentation_source_reconciler.run", fake_run)
    from tools.documentation_source_reconciler import changed_paths

    assert changed_paths("abc") == ("tools/a.py", "docs/b.md")
    assert ("ensure", "abc") in calls
    assert not any("--depth=2" in call for call in calls if isinstance(call, tuple))


def test_latest_material_success_follows_main_history_not_run_order(monkeypatch):
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.successful_main_runs",
        lambda: [
            {"headSha": "older", "databaseId": 1},
            {"headSha": "newer", "databaseId": 2},
        ],
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.first_parent_history",
        lambda: ("newer", "docs-only", "older"),
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.changed_paths",
        lambda revision: {
            "newer": ("implementation/runtime.py",),
            "older": ("tools/older.py",),
        }[revision],
    )
    from tools.documentation_source_reconciler import latest_material_success

    assert latest_material_success()["headSha"] == "newer"


def test_publish_uses_validated_current_main_when_histories_converge(monkeypatch, capsys):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return ""

    monkeypatch.setattr("tools.documentation_source_reconciler.run", fake_run)
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.latest_material_success",
        lambda: {
            "headSha": "material",
            "databaseId": 1,
            "url": "https://example.invalid/run/material",
        },
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.recorded_revision",
        lambda: "recorded",
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.first_parent_history",
        lambda: ("current-main", "material"),
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.successful_main_runs",
        lambda: [
            {
                "headSha": "current-main",
                "databaseId": 2,
                "url": "https://example.invalid/run/current-main",
            }
        ],
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.is_ancestor",
        lambda ancestor, descendant: (
            (ancestor, descendant)
            in {
                ("recorded", "current-main"),
                ("material", "current-main"),
            }
        ),
    )

    from tools.documentation_source_reconciler import publish_source_if_needed

    publish_source_if_needed()
    output = capsys.readouterr().out
    assert "SOURCE_DOCUMENTATION_RECONCILIATION=CONVERGED" in output
    assert "SOURCE_DOCUMENTATION_RECONCILIATION=PUBLISHED revision=current-main" in output
    publish_calls = [
        call for call in calls
        if call and call[0] == "bash"
    ]
    assert len(publish_calls) == 1
    assert publish_calls[0][3] == "current-main"
    assert publish_calls[0][4] == "2"
    assert publish_calls[0][5] == "https://example.invalid/run/current-main"


def test_publish_refuses_backward_candidate(monkeypatch, capsys):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return ""

    monkeypatch.setattr("tools.documentation_source_reconciler.run", fake_run)
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.latest_material_success",
        lambda: {"headSha": "older", "databaseId": 1, "url": "https://example.invalid/run/1"},
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.recorded_revision",
        lambda: "newer",
    )
    monkeypatch.setattr(
        "tools.documentation_source_reconciler.is_ancestor",
        lambda ancestor, descendant: False,
    )

    from tools.documentation_source_reconciler import publish_source_if_needed

    publish_source_if_needed()
    output = capsys.readouterr().out
    assert "SOURCE_DOCUMENTATION_RECONCILIATION=REFUSED_BACKWARD" in output
    assert not any(call and call[0] == "bash" for call in calls)


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


def test_required_checks_green_uses_repository_required_check_set(monkeypatch):
    class Result:
        stdout = '[{"name":"documentation","state":"SUCCESS","bucket":"pass"},{"name":"runtime-service","state":"SUCCESS","bucket":"pass"}]'
    monkeypatch.setattr("tools.documentation_source_reconciler.subprocess.run", lambda *a, **k: Result())
    from tools.documentation_source_reconciler import required_checks_green
    assert required_checks_green("123") is True


def test_required_checks_green_fails_on_pending(monkeypatch):
    class Result:
        stdout = '[{"name":"documentation","state":"PENDING","bucket":"pending"}]'
    monkeypatch.setattr("tools.documentation_source_reconciler.subprocess.run", lambda *a, **k: Result())
    from tools.documentation_source_reconciler import required_checks_green
    assert required_checks_green("123") is False
