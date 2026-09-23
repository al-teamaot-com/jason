from jason_mcp import server


def test_ticket_create_arguments_are_bounded_and_aliased():
    result = server._canonicalize_governed_action_arguments(
        "service.ticket.create",
        {
            "company_id": 123,
            "title": "Test ticket",
            "configuration_item_id": 456,
            "priority": 2,
        },
    )
    assert result == {
        "payload": {
            "companyID": 123,
            "title": "Test ticket",
            "configurationItemID": 456,
            "priority": 2,
        }
    }


def test_ticket_create_result_projects_only_verified_evidence():
    result = server._project_action_result(
        "service.ticket.create",
        {
            "data": {
                "itemId": 999,
                "jasonVerification": {
                    "readbackVerified": True,
                    "ticketId": 999,
                    "verifiedFields": ["companyID", "title"],
                },
                "unexpected": "must-not-escape",
            }
        },
    )
    assert result == {
        "raw_provider_evidence_exposed": False,
        "verification_available": True,
        "readback_verified": True,
        "ticket_id": 999,
        "verified_fields": ["companyID", "title"],
    }
