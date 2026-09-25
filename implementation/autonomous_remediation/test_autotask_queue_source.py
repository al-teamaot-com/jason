from .autotask_queue_source import AutotaskQueueDiscoveryConfig, AutotaskQueueSource


class Reads:
    def __init__(self):
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.entity.fields.describe":
            return {
                "status": "succeeded",
                "evidence": {"data": {"fields": [
                    {"name": "queueID", "picklistValues": [
                        {"value": "100", "label": "Jason", "isActive": True},
                        {"value": "200", "label": "Help Desk I", "isActive": True},
                    ]},
                    {"name": "priority", "picklistValues": [
                        {"value": "4", "label": "Critical", "sortOrder": 1, "isActive": True},
                        {"value": "1", "label": "High", "sortOrder": 2, "isActive": True},
                        {"value": "2", "label": "Medium", "sortOrder": 3, "isActive": True},
                    ]},
                ]}},
            }
        queue = arguments["filters"]["queueID"]
        status = arguments["status"]
        items = []
        if queue == 100 and status == "In Progress":
            items = [
                {"id": 10, "priority": 2, "queueID": 100, "status": 8, "assignedResourceID": 99,
                 "lastTrackedModificationDateTime": "2026-09-25T10:00:00Z", "title": "owned"},
                {"id": 11, "priority": 4, "queueID": 100, "status": 8, "assignedResourceID": None,
                 "lastTrackedModificationDateTime": "2026-09-25T10:01:00Z", "title": "critical"},
            ]
        if queue == 200 and status == "New":
            items = [
                {"id": 20, "priority": 1, "queueID": 200, "status": 1, "assignedResourceID": None,
                 "lastTrackedModificationDateTime": "2026-09-25T10:02:00Z", "title": "unassigned"},
                {"id": 21, "priority": 4, "queueID": 200, "status": 1, "assignedResourceID": 123,
                 "lastTrackedModificationDateTime": "2026-09-25T10:03:00Z", "title": "human-owned"},
            ]
        return {"status": "succeeded", "evidence": {"data": {"items": items}}}


def config(**overrides):
    values = dict(
        owned_queue_labels=("Jason",),
        discovery_queue_labels=("Help Desk I",),
        owned_status_labels=("In Progress",),
        discovery_status_labels=("New",),
        page_size=100,
        allow_assigned_discovery=False,
    )
    values.update(overrides)
    return AutotaskQueueDiscoveryConfig(**values)


def test_live_metadata_drives_queue_ids_and_priority_order():
    reads = Reads()
    source = AutotaskQueueSource(reads=reads, config=config())
    found = source.reconcile_candidates()
    by_id = {item.resource_id: item for item in found}
    assert set(by_id) == {"10", "11", "20"}
    assert by_id["11"].priority > by_id["20"].priority > by_id["10"].priority
    assert by_id["11"].source_queue == "Jason"
    assert by_id["20"].source_queue == "Help Desk I"


def test_non_jason_assigned_ticket_is_not_stolen_by_default():
    source = AutotaskQueueSource(reads=Reads(), config=config())
    found = source.reconcile_candidates()
    assert "21" not in {item.resource_id for item in found}


def test_owned_jason_ticket_remains_eligible_even_if_assigned():
    source = AutotaskQueueSource(reads=Reads(), config=config())
    found = {item.resource_id: item for item in source.reconcile_candidates()}
    assert found["10"].owned_by_jason is True


def test_source_version_uses_autotask_modification_marker():
    source = AutotaskQueueSource(reads=Reads(), config=config())
    found = {item.resource_id: item for item in source.reconcile_candidates()}
    assert found["20"].source_version == "2026-09-25T10:02:00Z"


def test_missing_queue_label_fails_closed():
    source = AutotaskQueueSource(
        reads=Reads(),
        config=config(discovery_queue_labels=("Missing Queue",)),
    )
    try:
        source.reconcile_candidates()
    except ValueError as exc:
        assert "Missing Queue" in str(exc)
    else:
        raise AssertionError("missing queue should fail closed")


def test_configured_jason_resource_assignment_is_eligible_outside_jason_queue():
    class JasonAssignedReads(Reads):
        def execute(self, capability, arguments):
            result = super().execute(capability, arguments)
            if capability == "service.ticket.search" and arguments["filters"]["queueID"] == 200 and arguments["status"] == "New":
                result = {"status": "succeeded", "evidence": {"data": {"items": [
                    {"id": 22, "priority": 4, "queueID": 200, "status": 1, "assignedResourceID": 999,
                     "lastTrackedModificationDateTime": "2026-09-25T10:04:00Z", "title": "jason assigned"},
                ]}}}
            return result

    source = AutotaskQueueSource(
        reads=JasonAssignedReads(),
        config=config(owned_resource_ids=(999,)),
    )
    found = {item.resource_id: item for item in source.reconcile_candidates()}
    assert "22" in found
    assert found["22"].owned_by_jason is True
    assert found["22"].urgent is True
