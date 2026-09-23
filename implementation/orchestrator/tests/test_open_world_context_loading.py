from types import SimpleNamespace

from orchestrator.dynamic_conversation_kernel import (
    DynamicConversationContext,
)
from orchestrator.open_world_teams_query_flow import (
    _load_or_create_context,
)


class Store:
    def __init__(self, existing=None):
        self.existing = existing
        self.calls = []

    def get(
        self,
        *,
        organization_id,
        principal_id,
        conversation_id,
    ):
        self.calls.append(
            {
                "organization_id": (
                    organization_id
                ),
                "principal_id": (
                    principal_id
                ),
                "conversation_id": (
                    conversation_id
                ),
            }
        )
        return self.existing


def principal():
    return SimpleNamespace(
        organization_id="org-1",
        principal_id="person-1",
    )


def identity():
    return SimpleNamespace(
        conversation_id="conversation-1",
    )


def test_existing_verified_context_is_reused():
    existing = DynamicConversationContext(
        conversation_id="conversation-1",
        principal_id="person-1",
        organization_id="org-1",
    )

    store = Store(
        existing=existing
    )

    result = _load_or_create_context(
        context_store=store,
        principal=principal(),
        identity=identity(),
    )

    assert result is existing

    assert store.calls == [
        {
            "organization_id": "org-1",
            "principal_id": "person-1",
            "conversation_id": (
                "conversation-1"
            ),
        }
    ]


def test_missing_context_is_created_from_authenticated_scope():
    store = Store()

    result = _load_or_create_context(
        context_store=store,
        principal=principal(),
        identity=identity(),
    )

    assert (
        result.organization_id
        == "org-1"
    )

    assert (
        result.principal_id
        == "person-1"
    )

    assert (
        result.conversation_id
        == "conversation-1"
    )

    assert result.entities == ()
