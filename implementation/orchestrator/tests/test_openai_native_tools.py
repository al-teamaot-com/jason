from orchestrator.openai_reasoning import (
    OpenAIStructuredJsonClient,
)


class Transport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)

        return {
            "id": "resp_test",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "governed_read",
                    "call_id": "call_test",
                    "arguments": (
                        '{"operation_ref":"op_test",'
                        '"information_goal":"read evidence"}'
                    ),
                }
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
        }


def test_native_tool_request_uses_responses_function_tools():
    transport = Transport()

    client = OpenAIStructuredJsonClient(
        api_key="test-secret",
        transport=transport,
        model="gpt-5-nano",
    )

    response = client.respond_with_tools(
        instructions="Use governed evidence.",
        input_items=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "question",
                    }
                ],
            }
        ],
        tools=[
            {
                "type": "function",
                "name": "governed_read",
                "description": "Read evidence",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "operation_ref": {
                            "type": "string",
                            "enum": [
                                "op_test"
                            ],
                        },
                        "information_goal": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "operation_ref",
                        "information_goal",
                    ],
                },
            }
        ],
        tool_choice="required",
    )

    assert response["status"] == "completed"

    body = transport.calls[0]["json"]

    assert body["model"] == "gpt-5-nano"
    assert body["store"] is False
    assert body["tool_choice"] == "required"
    assert body["tools"][0]["name"] == "governed_read"
    assert "text" not in body
