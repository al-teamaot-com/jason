import importlib.util
import io
import urllib.error
from unittest.mock import patch
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "change_integration_gate.py"
SPEC = importlib.util.spec_from_file_location("change_integration_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


class ChangeIntegrationGateTests(unittest.TestCase):
    def test_sensitive_paths(self):
        self.assertTrue(gate.sensitive("implementation/runtime_service/app.py"))
        self.assertTrue(gate.sensitive(".github/workflows/validate.yml"))
        self.assertTrue(gate.sensitive("CONTRIBUTING.md"))
        self.assertFalse(gate.sensitive("docs/sessions/proof.md"))

    def test_parse_acknowledged_bulleted_template_line(self):
        body = """
## Integration coordination

- Integration coordination: #123, #456
"""
        self.assertEqual(gate.parse_acknowledged(body), {123, 456})

    def test_parse_acknowledged_none(self):
        self.assertEqual(gate.parse_acknowledged("- Integration coordination: none"), set())


    def test_rate_limited_github_api_retries_and_preserves_validation(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"[]"
        limited = urllib.error.HTTPError(
            "https://api.github.com/repos/example/repo/pulls",
            403, "Forbidden", {"X-RateLimit-Remaining": "0"},
            io.BytesIO(b'{"message":"API rate limit exceeded"}')
        )
        with patch.object(gate.urllib.request, "urlopen", side_effect=[limited, Response()]) as send,              patch.object(gate.time, "sleep") as wait:
            self.assertEqual(gate.api_json("https://api.github.com/repos/example/repo/pulls", "test-token"), [])
        self.assertEqual(send.call_count, 2)
        wait.assert_called_once_with(5.0)

    def test_rate_limit_reset_header_is_honored_with_bounded_delay(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"[]"
        limited = urllib.error.HTTPError(
            "https://api.github.com/repos/example/repo/pulls",
            403, "Forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1060"},
            io.BytesIO(b'{"message":"API rate limit exceeded"}')
        )
        with patch.object(gate.time, "time", return_value=1000), \
             patch.object(gate.urllib.request, "urlopen", side_effect=[limited, Response()]) as send, \
             patch.object(gate.time, "sleep") as wait:
            self.assertEqual(
                gate.api_json("https://api.github.com/repos/example/repo/pulls", "test-token"),
                [],
            )
        self.assertEqual(send.call_count, 2)
        wait.assert_called_once_with(62.0)

    def test_rate_limit_reset_beyond_bound_fails_closed(self):
        limited = urllib.error.HTTPError(
            "https://api.github.com/repos/example/repo/pulls",
            403, "Forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "5000"},
            io.BytesIO(b'{"message":"API rate limit exceeded"}')
        )
        with patch.object(gate.time, "time", return_value=1000), \
             patch.object(gate.urllib.request, "urlopen", side_effect=[limited]) as send, \
             patch.object(gate.time, "sleep") as wait:
            with self.assertRaisesRegex(RuntimeError, "bounded recovery window"):
                gate.api_json("https://api.github.com/repos/example/repo/pulls", "test-token")
        self.assertEqual(send.call_count, 1)
        wait.assert_not_called()

    def test_ordinary_403_fails_closed_without_retry(self):
        denied = urllib.error.HTTPError(
            "https://api.github.com/repos/example/repo/pulls",
            403, "Forbidden", {},
            io.BytesIO(b'{"message":"Resource not accessible by integration"}')
        )
        with patch.object(gate.urllib.request, "urlopen", side_effect=[denied]) as send,              patch.object(gate.time, "sleep") as wait:
            with self.assertRaisesRegex(RuntimeError, "Resource not accessible"):
                gate.api_json("https://api.github.com/repos/example/repo/pulls", "test-token")
        self.assertEqual(send.call_count, 1)
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
