from __future__ import annotations

from types import SimpleNamespace

import pytest

from jason_runtime import procurement_web_read as subject


PUBLIC_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(
        subject.socket,
        "getaddrinfo",
        lambda host, port, type=None: [
            (subject.socket.AF_INET, subject.socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 443))
        ],
    )


def test_validate_url_requires_public_https() -> None:
    assert (
        subject.validate_public_https_url("https://www.staples.com/item")
        == "https://www.staples.com/item"
    )
    with pytest.raises(subject.ProcurementWebReadError, match="HTTPS"):
        subject.validate_public_https_url("http://www.staples.com/item")
def test_validate_url_rejects_private_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        subject.socket,
        "getaddrinfo",
        lambda host, port, type=None: [
            (subject.socket.AF_INET, subject.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(subject.ProcurementWebReadError, match="non-public"):
        subject.validate_public_https_url("https://example.test/item")


def test_extract_product_and_vendor_jsonld() -> None:
    html = """
    <html><head>
      <title>ThinkPad T14 - Staples</title>
      <meta property="og:title" content="ThinkPad T14">
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [
          {
            "@type": "Product",
            "name": "Lenovo ThinkPad T14",
            "sku": "ABC123",
            "mpn": "21XX0001US",
            "brand": {"@type":"Brand","name":"Lenovo"},
            "offers": {
              "@type":"Offer",
              "price":"899.99",
              "priceCurrency":"USD",
              "availability":"https://schema.org/InStock",
              "seller":{"@type":"Organization","name":"Staples"}
            }
          },
          {
            "@type":"Organization",
            "name":"Staples",
            "url":"https://www.staples.com",
            "telephone":"800-333-3330",
            "address":{
              "@type":"PostalAddress",
              "streetAddress":"500 Staples Dr",
              "addressLocality":"Framingham",
              "addressRegion":"MA",
              "postalCode":"01702"
            }
          }
        ]
      }
      </script>
    </head><body>Business laptop in stock.</body></html>
    """
    result = subject.extract_product_page(html)
    assert result["page_title"] == "ThinkPad T14 - Staples"
    assert result["products"][0]["sku"] == "ABC123"
    assert result["products"][0]["price"] == "899.99"
    assert result["products"][0]["brand"] == "Lenovo"
    assert result["organizations"][0]["name"] == "Staples"
    assert result["organizations"][0]["address"]["postal_code"] == "01702"
    assert "Business laptop" in result["visible_text_excerpt"]


def test_invoker_returns_bounded_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_fetch_html",
        lambda url, max_bytes: (
            "https://www.staples.com/item",
            "<html><head><title>Laptop</title></head><body>$899.99</body></html>",
            False,
        ),
    )
    request = SimpleNamespace(
        capability_name=subject.CAPABILITY,
        arguments={"url": "https://www.staples.com/item"},
    )
    resolution = SimpleNamespace(selected_provider_id=subject.PROVIDER)

    result = subject.ProcurementWebReadInvoker().invoke(
        request=request,
        resolution=resolution,
    )

    assert result.output["provider"] == subject.PROVIDER
    assert result.output["final_url"] == "https://www.staples.com/item"
    assert result.output["page_title"] == "Laptop"
    assert len(result.output["content_sha256"]) == 64


def test_invoker_rejects_unknown_arguments() -> None:
    request = SimpleNamespace(
        capability_name=subject.CAPABILITY,
        arguments={
            "url": "https://www.staples.com/item",
            "headers": {"Authorization": "secret"},
        },
    )
    resolution = SimpleNamespace(selected_provider_id=subject.PROVIDER)
    with pytest.raises(ValueError, match="unsupported"):
        subject.ProcurementWebReadInvoker().invoke(
            request=request,
            resolution=resolution,
        )
