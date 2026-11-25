from __future__ import annotations

import json

import pytest

from jason_runtime.approved_client_messages import (
    ApprovedClientMessageRegistryError,
    resolve_approved_client_message,
)


def _write_registry(tmp_path, templates):
    path = tmp_path / "approved.json"
    path.write_text(
        json.dumps({"version": 1, "templates": templates}),
        encoding="utf-8",
    )
    return path


def _template(**overrides):
    value = {
        "template_id": "example-v1",
        "workflow_id": "approved_workflow",
        "enabled": True,
        "title": "Example",
        "body": "Approved canned message.",
        "recipient_policy": "ticket_contact",
        "require_email_notifications": True,
    }
    value.update(overrides)
    return value


def test_resolve_exact_workflow_template_pair(tmp_path):
    path = _write_registry(tmp_path, [_template()])
    result = resolve_approved_client_message(
        workflow_id="approved_workflow",
        template_id="example-v1",
        path=path,
    )
    assert result.title == "Example"
    assert result.body == "Approved canned message."
    assert result.recipient_policy == "ticket_contact"
    assert result.require_email_notifications is True
    assert len(result.fingerprint) == 64


def test_rejects_template_for_different_workflow(tmp_path):
    path = _write_registry(tmp_path, [_template()])
    with pytest.raises(
        ApprovedClientMessageRegistryError,
        match="exact workflow/template pair",
    ):
        resolve_approved_client_message(
            workflow_id="different_workflow",
            template_id="example-v1",
            path=path,
        )


def test_disabled_template_is_not_resolvable(tmp_path):
    path = _write_registry(tmp_path, [_template(enabled=False)])
    with pytest.raises(
        ApprovedClientMessageRegistryError,
        match="exact workflow/template pair",
    ):
        resolve_approved_client_message(
            workflow_id="approved_workflow",
            template_id="example-v1",
            path=path,
        )


def test_duplicate_enabled_template_ids_fail_closed(tmp_path):
    path = _write_registry(
        tmp_path,
        [
            _template(workflow_id="approved_workflow"),
            _template(workflow_id="other_workflow"),
        ],
    )
    with pytest.raises(
        ApprovedClientMessageRegistryError,
        match="template_id must be unique",
    ):
        resolve_approved_client_message(
            workflow_id="approved_workflow",
            template_id="example-v1",
            path=path,
        )


def test_rejects_non_ticket_contact_recipient_policy(tmp_path):
    path = _write_registry(
        tmp_path,
        [_template(recipient_policy="arbitrary_email")],
    )
    with pytest.raises(
        ApprovedClientMessageRegistryError,
        match="recipient_policy must be ticket_contact",
    ):
        resolve_approved_client_message(
            workflow_id="approved_workflow",
            template_id="example-v1",
            path=path,
        )

@pytest.mark.parametrize(
    ("workflow", "template", "title", "body"),
    [
        ("ticket_progress", "approved-progress-v1", "Service Update",
         "Our team is investigating this request."),
        ("ticket_resolution", "approved-resolution-v1", "Resolution Update",
         "The reported issue has been resolved and verified."),
        ("maintenance_coordination", "approved-schedule-v1", "Maintenance Update",
         "We have scheduled the approved maintenance window."),
    ],
)
def test_non_question_approved_messages_use_same_generic_registry(
    tmp_path, workflow, template, title, body,
):
    """Non-question notices are ordinary, exact source-owned templates."""
    path = _write_registry(
        tmp_path,
        [_template(
            workflow_id=workflow, template_id=template, title=title, body=body,
        )],
    )
    resolved = resolve_approved_client_message(
        workflow_id=workflow, template_id=template, path=path,
    )
    assert (resolved.title, resolved.body) == (title, body)
    assert resolved.workflow_id == workflow
    with pytest.raises(
        ApprovedClientMessageRegistryError, match="exact workflow/template pair"
    ):
        resolve_approved_client_message(
            workflow_id="unapproved_workflow",
            template_id=template,
            path=path,
        )
