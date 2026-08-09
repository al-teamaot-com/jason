from unittest import TestCase
from unittest.mock import patch

from connectors.microsoft_graph.graph_client_credentials import (
    MicrosoftGraphClientCredentialConfig,
    MicrosoftGraphClientCredentialTokenProvider,
)


class Secrets:
    def __init__(self, value="secret-value"):
        self.value = value
        self.references = []

    def get_secret(self, reference):
        self.references.append(reference)
        return self.value


class Application:
    def __init__(self, result):
        self.result = result
        self.scopes = None

    def acquire_token_for_client(self, *, scopes):
        self.scopes = scopes
        return self.result


class GraphClientCredentialTests(TestCase):
    def config(self, **overrides):
        values = dict(
            tenant_id="tenant-1",
            client_id="client-1",
            client_secret_reference="openbao://microsoft/graph/client-secret",
        )
        values.update(overrides)
        return MicrosoftGraphClientCredentialConfig(**values)

    @patch("connectors.microsoft_graph.graph_client_credentials.msal.ConfidentialClientApplication")
    def test_acquires_graph_default_scope_without_persisting_secret(self, factory):
        application = Application({"access_token": " access-token "})
        factory.return_value = application
        secrets = Secrets()
        provider = MicrosoftGraphClientCredentialTokenProvider(self.config(), secrets)

        self.assertEqual(provider.access_token(), "access-token")
        self.assertEqual(secrets.references, ["openbao://microsoft/graph/client-secret"])
        factory.assert_called_once_with(
            client_id="client-1",
            authority="https://login.microsoftonline.com/tenant-1",
            client_credential="secret-value",
        )
        self.assertEqual(application.scopes, ["https://graph.microsoft.com/.default"])
        self.assertNotIn("secret-value", repr(provider))

    def test_rejects_noncanonical_authority(self):
        provider = MicrosoftGraphClientCredentialTokenProvider(
            self.config(authority_host="https://evil.example"), Secrets()
        )
        with self.assertRaises(ValueError):
            provider.access_token()

    def test_rejects_non_graph_scope(self):
        provider = MicrosoftGraphClientCredentialTokenProvider(
            self.config(scope="https://management.azure.com/.default"), Secrets()
        )
        with self.assertRaises(ValueError):
            provider.access_token()

    def test_fails_closed_when_secret_missing(self):
        provider = MicrosoftGraphClientCredentialTokenProvider(self.config(), Secrets(""))
        with self.assertRaises(PermissionError):
            provider.access_token()

    @patch("connectors.microsoft_graph.graph_client_credentials.msal.ConfidentialClientApplication")
    def test_token_failure_does_not_expose_secret(self, factory):
        factory.return_value = Application(
            {"error": "invalid_client", "error_description": "credential rejected"}
        )
        provider = MicrosoftGraphClientCredentialTokenProvider(self.config(), Secrets("TOP-SECRET"))
        with self.assertRaises(PermissionError) as caught:
            provider.access_token()
        self.assertNotIn("TOP-SECRET", str(caught.exception))
