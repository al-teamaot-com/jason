import unittest

from connectors.microsoft_graph.sharepoint_reader import AOTAdminSharePointReader, APPROVED_SITE_ID


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        return "synthetic-test-token"


class Transport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["url"].endswith("/drives"):
            return {"value": [{"id": "allowed-drive", "name": "Docs", "webUrl": "https://example.invalid"}]}
        return {"id": "file1", "name": "test.txt", "file": {"mimeType": "text/plain"},
                "parentReference": {"driveId": "allowed-drive"}, "eTag": "v1"}


class SharePointReaderTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.reader = AOTAdminSharePointReader(Tokens(), self.transport, "trusted-tenant")

    def test_allowed_file_metadata(self):
        item = self.reader.item_metadata(tenant_id="trusted-tenant", drive_id="allowed-drive", item_id="file1")
        self.assertEqual(item["siteId"], APPROVED_SITE_ID)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertTrue(all(c["method"] == "GET" for c in self.transport.calls))

    def test_tenant_mismatch_fails_before_transport(self):
        with self.assertRaises(PermissionError):
            self.reader.list_libraries(tenant_id="foreign-tenant")
        self.assertFalse(self.transport.calls)

    def test_unapproved_drive_fails_before_item_read(self):
        with self.assertRaises(PermissionError):
            self.reader.item_metadata(tenant_id="trusted-tenant", drive_id="foreign-drive", item_id="file1")
        self.assertEqual(len(self.transport.calls), 1)

    def test_path_selector_rejected(self):
        with self.assertRaises(ValueError):
            self.reader.item_metadata(tenant_id="trusted-tenant", drive_id="allowed-drive", item_id="../file1")
        self.assertFalse(self.transport.calls)

    def test_wrong_site_config_rejected(self):
        with self.assertRaises(ValueError):
            AOTAdminSharePointReader(Tokens(), self.transport, "trusted-tenant", "other-site")

    def test_unbounded_pagination_fails_closed(self):
        self.transport.request = lambda **kw: {"value": [], "@odata.nextLink": "unexpected"}
        with self.assertRaises(Exception):
            self.reader.list_libraries(tenant_id="trusted-tenant")


if __name__ == "__main__":
    unittest.main()

class SharePointExtendedTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.reader = AOTAdminSharePointReader(Tokens(), self.transport, "trusted-tenant")

    def test_list_files_rejects_unauthorized_drive(self):
        with self.assertRaises(PermissionError):
            self.reader.list_files(tenant_id="trusted-tenant", drive_id="other")
        self.assertEqual(len(self.transport.calls), 1)

    def test_folder_pagination_fails_closed(self):
        old = self.transport.request
        def request(**kw):
            if kw["url"].endswith("/children"):
                return {"value": [], "@odata.nextLink": "next"}
            return old(**kw)
        self.transport.request = request
        with self.assertRaises(Exception):
            self.reader.list_files(tenant_id="trusted-tenant", drive_id="allowed-drive")

    def test_file_size_rejects_download(self):
        old = self.transport.request
        def request(**kw):
            data = old(**kw)
            if kw["url"].endswith("/items/file1"):
                data["size"] = 2000000
            return data
        self.transport.request = request
        with self.assertRaises(ValueError):
            self.reader.file_bytes(tenant_id="trusted-tenant", drive_id="allowed-drive", item_id="file1")

    def test_content_read_bounded_and_get_only(self):
        old = self.transport.request
        def request(**kw):
            data = old(**kw)
            if kw["url"].endswith("/items/file1"):
                data["size"] = 3
            return data
        self.transport.request = request
        self.transport.request_bytes = lambda **kw: b"abc"
        self.assertEqual(self.reader.file_bytes(tenant_id="trusted-tenant", drive_id="allowed-drive", item_id="file1"), b"abc")
