from orchestrator.dynamic_conversation_intent import (
    GroundedConversationIntentBuilder,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicConversationContext,
)
from orchestrator.governed_query import (
    GovernedQueryPlan,
)
from orchestrator.open_world_query_planning import (
    OpenWorldQueryPlan,
    OpenWorldQuerySource,
)
from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from orchestrator.open_world_selector_grounding import (
    OpenWorldGroundedSelectorResolver,
)


class BindingClient:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": (
                    max_output_tokens
                ),
            }
        )
        return self.proposal


def resource(
    *,
    resource_type="thing",
    collection_supported=False,
    selector_keys=None,
):
    effective_selector_keys = (
        tuple(selector_keys)
        if selector_keys is not None
        else (
            ("name",)
            if not collection_supported
            else ()
        )
    )

    return DiscoveredResourceSchema(
        provider_id="provider-a",
        capability_name="thing.search",
        resource_type=resource_type,
        operation="search",
        collection_supported=(
            collection_supported
        ),
        selector_keys=(
            effective_selector_keys
        ),
        fields=(
            DiscoveredField(
                name="value",
                path="branch.value",
                value_type="string",
            ),
        ),
    )


def context():
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-1",
        organization_id="org-1",
    )


def test_exact_literal_makes_selector_only_resource_eligible():
    item = resource()

    client = BindingClient(
        {
            "bindings": [
                {
                    "argument": "name",
                    "source_type": "literal",
                    "source_id": None,
                    "literal": "NODE-77",
                }
            ]
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    result = resolver.ground(
        human_text=(
            "Show the current value for NODE-77"
        ),
        context=context(),
        catalog=OpenWorldResourceCatalog(
            resources=(
                item,
            )
        ),
    )

    assert (
        result.catalog.resources
        == (
            item,
        )
    )

    assert (
        result.selectors_by_handle[
            item.resource_handle
        ]
        == "NODE-77"
    )


def test_ungrounded_selector_only_resource_is_not_eligible():
    selector_only = resource()

    collection = resource(
        resource_type="collection-thing",
        collection_supported=True,
    )

    client = BindingClient(
        {
            "bindings": [],
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    result = resolver.ground(
        human_text=(
            "Show all available information"
        ),
        context=context(),
        catalog=OpenWorldResourceCatalog(
            resources=(
                selector_only,
                collection,
            )
        ),
    )

    assert result.catalog.resources == (
        collection,
    )

    assert (
        selector_only.resource_handle
        not in result.selectors_by_handle
    )


def test_active_verified_entity_can_ground_selector():
    item = resource()

    verified = ConversationEntity(
        ref="entity-1",
        kind="thing",
        canonical_id="durable-77",
        display_name="NODE-77",
        provenance="verified evidence",
    )

    verified_context = DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-1",
        organization_id="org-1",
        entities=(
            verified,
        ),
        active_entity_refs={
            "thing": "entity-1",
        },
    )

    client = BindingClient(
        {
            "bindings": [
                {
                    "argument": "name",
                    "source_type": "entity",
                    "source_id": (
                        "entity-1:display_name"
                    ),
                    "literal": None,
                }
            ]
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    result = resolver.ground(
        human_text=(
            "What about that resource?"
        ),
        context=verified_context,
        catalog=OpenWorldResourceCatalog(
            resources=(
                item,
            )
        ),
    )

    assert (
        result.selectors_by_handle[
            item.resource_handle
        ]
        == "NODE-77"
    )


def test_collection_resource_accepts_safe_optional_grounded_selector():
    item = resource(
        collection_supported=True,
        selector_keys=(
            "name",
            "resource_id",
        ),
    )

    client = BindingClient(
        {
            "bindings": [
                {
                    "argument": "name",
                    "source_type": "literal",
                    "source_id": None,
                    "literal": "50282",
                }
            ]
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    grounded = resolver.ground(
        human_text=(
            "do we have a device 50282"
        ),
        context=context(),
        catalog=OpenWorldResourceCatalog(
            resources=(
                item,
            )
        ),
    )

    assert grounded.catalog.resources == (
        item,
    )

    assert (
        grounded.selectors_by_handle[
            item.resource_handle
        ]
        == "50282"
    )


def test_collection_resource_remains_eligible_without_grounded_selector():
    item = resource(
        collection_supported=True,
        selector_keys=(
            "name",
            "resource_id",
        ),
    )

    client = BindingClient(
        {
            "bindings": [],
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    grounded = resolver.ground(
        human_text=(
            "list the managed devices"
        ),
        context=context(),
        catalog=OpenWorldResourceCatalog(
            resources=(
                item,
            )
        ),
    )

    assert grounded.catalog.resources == (
        item,
    )

    assert (
        item.resource_handle
        not in grounded.selectors_by_handle
    )


def test_bind_plan_forwards_optional_selector_to_collection_source():
    item = resource(
        collection_supported=True,
        selector_keys=(
            "name",
            "resource_id",
        ),
    )

    source = OpenWorldQuerySource(
        alias="r",
        resource_handle=(
            item.resource_handle
        ),
        field_paths=(
            "branch.value",
        ),
        selector_reference=None,
    )

    plan = OpenWorldQueryPlan(
        sources=(
            source,
        ),
        relational_plan=GovernedQueryPlan(
            sources=(
                "r",
            ),
        ),
        answer_mode="scalar",
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [],
                }
            )
        )
    )

    bound = resolver.bind_plan(
        plan=plan,
        catalog=OpenWorldResourceCatalog(
            resources=(
                item,
            )
        ),
        selectors_by_handle={
            item.resource_handle: "50282",
        },
    )

    assert (
        bound.sources[0].selector_reference
        == "50282"
    )


def test_selector_only_resource_still_requires_grounded_selector():
    item = resource(
        collection_supported=False,
        selector_keys=(
            "name",
        ),
    )

    source = OpenWorldQuerySource(
        alias="r",
        resource_handle=(
            item.resource_handle
        ),
        field_paths=(
            "branch.value",
        ),
        selector_reference=None,
    )

    plan = OpenWorldQueryPlan(
        sources=(
            source,
        ),
        relational_plan=GovernedQueryPlan(
            sources=(
                "r",
            ),
        ),
        answer_mode="scalar",
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [],
                }
            )
        )
    )

    try:
        resolver.bind_plan(
            plan=plan,
            catalog=OpenWorldResourceCatalog(
                resources=(
                    item,
                )
            ),
            selectors_by_handle={},
        )
    except Exception as error:
        assert (
            "has no grounded selector"
            in str(error)
        )
    else:
        raise AssertionError(
            "selector-only resource must fail closed "
            "without a grounded selector"
        )


def test_rejected_selector_candidate_does_not_abort_other_eligible_resource():
    collection = resource(
        resource_type="thing-collection",
        collection_supported=True,
        selector_keys=(
            "name",
        ),
    )

    verified_only = DiscoveredResourceSchema(
        provider_id="provider-a",
        capability_name="thing.read",
        resource_type="thing",
        operation="read",
        collection_supported=False,
        selector_keys=(
            "resource_id",
        ),
        fields=(
            DiscoveredField(
                name="value",
                path="branch.value",
                value_type="string",
            ),
        ),
        selector_source_policy=(
            (
                "resource_id",
                "verified_entity_only",
            ),
        ),
    )

    class SequencedClient:
        def __init__(self):
            self.calls = 0

        def complete(
            self,
            *,
            system,
            user,
            schema,
            max_output_tokens,
        ):
            self.calls += 1

            if self.calls == 1:
                return {
                    "bindings": [
                        {
                            "argument": "name",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "NODE-77",
                        }
                    ]
                }

            return {
                "bindings": [
                    {
                        "argument": "resource_id",
                        "source_type": "literal",
                        "source_id": None,
                        "literal": "NODE-77",
                    }
                ]
            }

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=SequencedClient()
        )
    )

    grounded = resolver.ground(
        human_text="Find NODE-77",
        context=context(),
        catalog=OpenWorldResourceCatalog(
            resources=(
                collection,
                verified_only,
            )
        ),
    )

    assert collection in grounded.catalog.resources
    assert verified_only not in grounded.catalog.resources

    assert (
        grounded.selectors_by_handle[
            collection.resource_handle
        ]
        == "NODE-77"
    )


def test_rejected_only_candidate_still_fails_closed():
    verified_only = DiscoveredResourceSchema(
        provider_id="provider-a",
        capability_name="thing.read",
        resource_type="thing",
        operation="read",
        collection_supported=False,
        selector_keys=(
            "resource_id",
        ),
        fields=(
            DiscoveredField(
                name="value",
                path="branch.value",
                value_type="string",
            ),
        ),
        selector_source_policy=(
            (
                "resource_id",
                "verified_entity_only",
            ),
        ),
    )

    client = BindingClient(
        {
            "bindings": [
                {
                    "argument": "resource_id",
                    "source_type": "literal",
                    "source_id": None,
                    "literal": "NODE-77",
                }
            ]
        }
    )

    resolver = OpenWorldGroundedSelectorResolver(
        builder=GroundedConversationIntentBuilder(
            client=client
        )
    )

    try:
        resolver.ground(
            human_text="Read NODE-77",
            context=context(),
            catalog=OpenWorldResourceCatalog(
                resources=(
                    verified_only,
                )
            ),
        )
    except Exception as error:
        assert (
            "no executable governed resources"
            in str(error)
        )
    else:
        raise AssertionError(
            "a rejected sole candidate must fail closed"
        )
