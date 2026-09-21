from __future__ import annotations

import base64
import hashlib
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

from connectors.it_glue.operations import resolve_operation
from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import (
    ConnectorRequest,
    ConnectorResult,
    ConnectorTransportError,
    require_capability,
)




class ItGlueAttachmentDownloadError(ConnectorTransportError):
    error_code = "IT_GLUE_ATTACHMENT_DOWNLOAD_FAILED"


class ItGlueAttachmentHtmlResponseError(ItGlueAttachmentDownloadError):
    error_code = "IT_GLUE_ATTACHMENT_HTML_RESPONSE"


class ItGlueAttachmentDownloadUrlError(ItGlueAttachmentDownloadError):
    error_code = "IT_GLUE_ATTACHMENT_DOWNLOAD_URL_INVALID"


class ItGlueConnector(ConnectorBase):
    provider_name = "it_glue"
    logical_secret = "it_glue.readonly"
    base_url = "https://api.itglue.com"

    capabilities = frozenset(
        {
            "it_glue.entity.get",
            "it_glue.entity.query",
            "it_glue.organization.get",
            "it_glue.configuration.search",
            "it_glue.flexible_asset.search",
            "it_glue.document.search",
            "it_glue.document.get",
            "it_glue.document.attachment.search",
            "it_glue.document.attachment.get",
            "it_glue.document.attachment.content.get",
            "it_glue.relationships.list",
        }
    )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.context.capability != "it_glue.document.attachment.content.get":
            return super().execute(request)

        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        document_id = int(request.arguments["document_id"])
        attachment_id = int(request.arguments["attachment_id"])
        max_bytes = int(request.arguments.get("max_bytes", 10 * 1024 * 1024))

        headers = {
            "x-api-key": credentials["api_key"],
            "Accept": "application/vnd.api+json",
        }
        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": "document_attachment_content"},
        )
        parent_document = self._transport.request(
            method="GET",
            url=f"{self.base_url}/documents/{document_id}",
            headers=headers,
            params={"include": "authorized_users"},
            timeout_seconds=30.0,
        )
        self._audit.record(
            "connector.attachment.parent_loaded",
            request.context,
            {"provider": self.provider_name, "document_id": document_id},
        )
        attachment_payload = self._transport.request(
            method="GET",
            url=f"{self.base_url}/documents/{document_id}/relationships/attachments/{attachment_id}",
            headers=headers,
            timeout_seconds=30.0,
        )
        self._audit.record(
            "connector.attachment.metadata_loaded",
            request.context,
            {"provider": self.provider_name, "attachment_id": attachment_id},
        )
        resource = attachment_payload.get("data") if isinstance(attachment_payload, Mapping) else None
        attributes = resource.get("attributes") if isinstance(resource, Mapping) else None
        if not isinstance(attributes, Mapping):
            raise ValueError("IT Glue attachment metadata is missing")
        download_url = str(attributes.get("download-url") or "").strip()
        if not download_url:
            raise ItGlueAttachmentDownloadUrlError("IT Glue attachment download URL is missing")
        if download_url.startswith("/"):
            download_url = urljoin(self.base_url + "/", download_url.lstrip("/"))
        parts = urlsplit(download_url)
        host = (parts.hostname or "").casefold()
        if parts.scheme not in {"http", "https"} or not (host == "itglue.com" or host.endswith(".itglue.com")):
            raise ItGlueAttachmentDownloadUrlError("IT Glue attachment download URL is outside the approved provider domain")
        if parts.scheme == "http":
            download_url = urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))

        self._audit.record(
            "connector.attachment.download_started",
            request.context,
            {"provider": self.provider_name, "provider_domain_validated": True},
        )
        raw = self._transport.request_bytes(
            method="GET",
            url=download_url,
            headers={"x-api-key": credentials["api_key"]},
            timeout_seconds=30.0,
            max_bytes=max_bytes,
        )
        self._audit.record(
            "connector.attachment.bytes_loaded",
            request.context,
            {"provider": self.provider_name, "content_bytes": len(raw)},
        )
        prefix = raw[:512].lstrip().lower()
        if (
            prefix.startswith(b"<!doctype html")
            or prefix.startswith(b"<html")
            or b"<title>it glue</title>" in prefix
        ):
            # IT Glue documents only a web-app download URL. Before concluding that
            # binary download requires a browser session, make one bounded read-only
            # probe against the API host using the exact provider-supplied path. This
            # does not guess IDs or broaden scope, and remains under the same API key.
            api_candidate = urlunsplit(
                ("https", urlsplit(self.base_url).netloc, parts.path, parts.query, "")
            )
            self._audit.record(
                "connector.attachment.api_path_probe_started",
                request.context,
                {
                    "provider": self.provider_name,
                    "path": parts.path,
                },
            )
            try:
                candidate_raw = self._transport.request_bytes(
                    method="GET",
                    url=api_candidate,
                    headers={"x-api-key": credentials["api_key"]},
                    timeout_seconds=30.0,
                    max_bytes=max_bytes,
                )
            except ConnectorTransportError:
                raise ItGlueAttachmentHtmlResponseError(
                    "IT Glue attachment web download requires non-API authentication"
                )
            candidate_prefix = candidate_raw[:512].lstrip().lower()
            if (
                candidate_prefix.startswith(b"<!doctype html")
                or candidate_prefix.startswith(b"<html")
                or b"<title>it glue</title>" in candidate_prefix
            ):
                raise ItGlueAttachmentHtmlResponseError(
                    "IT Glue attachment web download requires non-API authentication"
                )
            raw = candidate_raw
            self._audit.record(
                "connector.attachment.api_path_probe_succeeded",
                request.context,
                {"provider": self.provider_name, "content_bytes": len(raw)},
            )

        safe_attributes = {
            str(key): value
            for key, value in attributes.items()
            if str(key) != "download-url"
        }
        result = {
            "parent_document": parent_document,
            "attachment": {
                "id": str(resource.get("id") or attachment_id),
                "type": str(resource.get("type") or "attachments"),
                "attributes": safe_attributes,
            },
            "content_base64": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content_bytes": len(raw),
        }
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name, "operation": "document_attachment_content"},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=result,
        )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        method, path, params = resolve_operation(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method=method,
            url=f"{self.base_url.rstrip('/')}{path}",
            headers={
                "x-api-key": credentials["api_key"],
                "Accept": "application/vnd.api+json",
            },
            params=params,
            audit_operation=path,
        )
