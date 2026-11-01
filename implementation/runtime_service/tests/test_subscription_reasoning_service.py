from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from jason_runtime.subscription_reasoning_service import (
    CodexSubscriptionReasoner,
    SubscriptionReasoningError,
)


class Runner:
    def __init__(self, *, auth_rc=0, exec_rc=0, stderr="", result=None):
        self.auth_rc = auth_rc
        self.exec_rc = exec_rc
        self.stderr = stderr
        self.result = result if result is not None else {"ok": True}
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        if len(argv) >= 3 and argv[1:3] == ["login", "status"]:
            return subprocess.CompletedProcess(argv, self.auth_rc)
        output_index = argv.index("--output-last-message") + 1
        Path(argv[output_index]).write_text(json.dumps(self.result), encoding="utf-8")
        return subprocess.CompletedProcess(
            argv, self.exec_rc, stdout="", stderr=self.stderr
        )


def test_subscription_reasoner_runs_ephemeral_read_only_codex():
    runner = Runner(result={"ok": True})
    reasoner = CodexSubscriptionReasoner(runner=runner, model="gpt-test")
    result = reasoner.complete(
        system="system",
        user="user",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        max_output_tokens=64,
    )
    assert result == {"ok": True}
    command = runner.calls[1][0]
    assert "exec" in command
    assert "--ephemeral" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--model" in command
    assert "gpt-test" in command


def test_subscription_reasoner_fails_closed_without_chatgpt_auth():
    reasoner = CodexSubscriptionReasoner(runner=Runner(auth_rc=1))
    with pytest.raises(SubscriptionReasoningError) as exc:
        reasoner.complete(
            system="s", user="u", schema={"type": "object"},
            max_output_tokens=16,
        )
    assert exc.value.code == "subscription_auth_required"
    assert exc.value.status == 401


def test_subscription_reasoner_maps_plan_limit_without_leaking_stderr():
    reasoner = CodexSubscriptionReasoner(
        runner=Runner(exec_rc=1, stderr="usage limit exceeded private-detail")
    )
    with pytest.raises(SubscriptionReasoningError) as exc:
        reasoner.complete(
            system="s", user="u", schema={"type": "object"},
            max_output_tokens=16,
        )
    assert exc.value.code == "subscription_sharing_usage_limit_exceeded"
    assert exc.value.status == 429
    assert "private-detail" not in str(exc.value)
