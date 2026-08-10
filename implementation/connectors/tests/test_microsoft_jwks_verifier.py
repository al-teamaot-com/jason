from __future__ import annotations

import base64
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from connectors.microsoft_graph.microsoft_jwks_verifier import (
    MicrosoftJwksPolicy,
    MicrosoftJwksVerificationError,
    MicrosoftJwksVerifier,
)


class FakeFetcher:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        value = self.documents[url]
        if isinstance(value, list):
            return value.pop(0)
        return value


def token_with_header(header):
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b"{}").rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(b"signature").rstrip(b"=").decode()
    return f"{encoded}.{payload}.{signature}"


class MicrosoftJwksVerifierTests(unittest.TestCase):
    tenant = "tenant-1"
    discovery = "https://login.microsoftonline.com/tenant-1/v2.0/.well-known/openid-configuration"
    jwks = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    now = datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc)

    def make(self, keys=None, jwks_uri=None):
        fetcher = FakeFetcher({
            self.discovery: {"jwks_uri": jwks_uri or self.jwks},
            self.jwks: {"keys": keys or [{"kid": "key-1", "kty": "RSA", "use": "sig", "alg": "RS256", "n": "AQAB", "e": "AQAB"}]},
        })
        verifier = MicrosoftJwksVerifier(fetcher, MicrosoftJwksPolicy(self.tenant), clock=lambda: self.now)
        return verifier, fetcher

    @patch("connectors.microsoft_graph.microsoft_jwks_verifier.jwt.decode")
    @patch("connectors.microsoft_graph.microsoft_jwks_verifier.jwt.algorithms.RSAAlgorithm.from_jwk")
    def test_approved_key_is_used_for_crypto_verification(self, from_jwk, decode):
        from_jwk.return_value = object()
        decode.return_value = {"tid": self.tenant}
        verifier, fetcher = self.make()
        claims = verifier.verify_signature(token_with_header({"alg": "RS256", "kid": "key-1"}))
        self.assertEqual(claims["tid"], self.tenant)
        self.assertEqual(fetcher.calls, [self.discovery, self.jwks])
        decode.assert_called_once()

    def test_algorithm_confusion_fails_before_network(self):
        verifier, fetcher = self.make()
        with self.assertRaises(MicrosoftJwksVerificationError):
            verifier.verify_signature(token_with_header({"alg": "HS256", "kid": "key-1"}))
        self.assertEqual(fetcher.calls, [])

    def test_non_microsoft_jwks_uri_is_rejected(self):
        verifier, _ = self.make(jwks_uri="https://evil.example/keys")
        with self.assertRaises(MicrosoftJwksVerificationError):
            verifier.verify_signature(token_with_header({"alg": "RS256", "kid": "key-1"}))

    def test_unknown_kid_triggers_one_controlled_refresh_then_fails(self):
        verifier, fetcher = self.make()
        with self.assertRaises(MicrosoftJwksVerificationError):
            verifier.verify_signature(token_with_header({"alg": "RS256", "kid": "rotated"}))
        self.assertEqual(fetcher.calls, [self.discovery, self.jwks, self.discovery, self.jwks])

    def test_cache_avoids_retrieval_until_expiry(self):
        verifier, fetcher = self.make()
        with patch("connectors.microsoft_graph.microsoft_jwks_verifier.jwt.algorithms.RSAAlgorithm.from_jwk", return_value=object()), patch("connectors.microsoft_graph.microsoft_jwks_verifier.jwt.decode", return_value={}):
            token = token_with_header({"alg": "RS256", "kid": "key-1"})
            verifier.verify_signature(token)
            verifier.verify_signature(token)
        self.assertEqual(fetcher.calls, [self.discovery, self.jwks])

    def test_unapproved_key_types_are_not_cached(self):
        verifier, _ = self.make(keys=[{"kid": "ec", "kty": "EC", "use": "sig", "alg": "ES256"}])
        with self.assertRaises(MicrosoftJwksVerificationError):
            verifier.verify_signature(token_with_header({"alg": "RS256", "kid": "ec"}))

    def test_policy_rejects_algorithm_expansion(self):
        with self.assertRaises(ValueError):
            MicrosoftJwksPolicy(self.tenant, allowed_algorithms=("RS256", "HS256")).validate()


if __name__ == "__main__":
    unittest.main()
