from __future__ import annotations

import unittest

from connectors.microsoft_graph.teams_graph_transport import MicrosoftGraphTeamsMessageTransport


class TokenProvider:
    def __init__(self, token="token-value"):
        self.token = token
        self.calls = 0

    def access_token(self):
        self.calls += 1
        return self.token


class FakeHttp:
    def __init__(self, response=None, error=None):
        self.response = response or {"id": "message-1", "createdDateTime": "2026-08-09T16:00:00Z"}
        self.error = error
        self.calls = []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class TeamsGraphTransportTests(unittest.TestCase):
    def test_posts_only_to_canonical_graph_v1_channel_message_endpoint(self):
        token = TokenProvider()
        http = FakeHttp()
        transport = MicrosoftGraphTeamsMessageTransport(token_provider=token, http=http)

        result = transport.post_channel_message(
            team_id="team/id",
            channel_id="channel id",
            message={"body": {"content": "approved payload"}},
        )

        self.assertEqual("message-1", result["id"])
        self.assertEqual(1, token.calls)
        call = http.calls[0]
        self.assertEqual(
            "https://graph.microsoft.com/v1.0/teams/team%2Fid/channels/channel%20id/messages",
            call["url"],
        )
        self.assertEqual("Bearer token-value", call["headers"]["Authorization"])
        self.assertEqual("application/json", call["headers"]["Content-Type"])
        self.assertEqual({"body": {"content": "approved payload"}}, call["body"])
        self.assertEqual(20.0, call["timeout_seconds"])

    def test_rejects_noncanonical_graph_base_url(self):
        with self.assertRaises(ValueError):
            MicrosoftGraphTeamsMessageTransport(
                token_provider=TokenProvider(),
                http=FakeHttp(),
                graph_base_url="https://attacker.example/v1.0",
            )

    def test_rejects_missing_or_malformed_access_token_before_http(self):
        for token_value in ("", "   ", "token with spaces"):
            http = FakeHttp()
            transport = MicrosoftGraphTeamsMessageTransport(
                token_provider=TokenProvider(token_value),
                http=http,
            )
            with self.assertRaises(PermissionError):
                transport.post_channel_message(team_id="team", channel_id="channel", message={"x": 1})
            self.assertEqual([], http.calls)

    def test_rejects_empty_message_and_identifiers_before_token_request(self):
        token = TokenProvider()
        transport = MicrosoftGraphTeamsMessageTransport(token_provider=token, http=FakeHttp())
        for team_id, channel_id, message in (
            ("", "channel", {"x": 1}),
            ("team", "", {"x": 1}),
            ("team", "channel", {}),
        ):
            with self.assertRaises(ValueError):
                transport.post_channel_message(team_id=team_id, channel_id=channel_id, message=message)
        self.assertEqual(0, token.calls)

    def test_rejects_response_without_message_id(self):
        transport = MicrosoftGraphTeamsMessageTransport(
            token_provider=TokenProvider(),
            http=FakeHttp(response={"createdDateTime": "2026-08-09T16:00:00Z"}),
        )
        with self.assertRaises(RuntimeError):
            transport.post_channel_message(team_id="team", channel_id="channel", message={"x": 1})

    def test_timeout_policy_is_bounded(self):
        for timeout in (0, -1, 61):
            with self.assertRaises(ValueError):
                MicrosoftGraphTeamsMessageTransport(
                    token_provider=TokenProvider(),
                    http=FakeHttp(),
                    timeout_seconds=timeout,
                )


if __name__ == "__main__":
    unittest.main()
