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


def test_extract_numeric_jsonld_price_without_confusing_regular_price() -> None:
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@type": "Product",
        "name": "Lenovo ThinkPad L16 G2",
        "sku": "24667541",
        "mpn": "21SBS2CB00-W11P",
        "offers": {
          "@type": "Offer",
          "price": 879.99,
          "priceCurrency": "USD",
          "availability": "https://schema.org/LimitedAvailability",
          "seller": {"@type":"Organization","name":"Staples"}
        }
      }
      </script>
    </head><body>Final price is $879.99. Original price is $1,299.99.</body></html>
    """
    result = subject.extract_product_page(html)
    product = result["products"][0]
    assert product["price"] == "879.99"
    assert product["currency"] == "USD"
    assert product["sku"] == "24667541"


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



def test_rendered_text_fallback_ignores_scripts_and_prefers_mpn() -> None:
    html = """
    <html><head>
      <title>Plugable USB C to VGA Adapter - Newegg.com</title>
      <meta property="og:title" content="Plugable USB C to VGA Adapter">
      <style>.fake:after { content: '$999.99'; }</style>
      <script>window.fakePrice = '$888.88';</script>
    </head><body>
      <div>Item#: <em>9SIA2XBBKZ0313</em></div>
      <div data-pp-amount="19.95"></div>
      <script src="https://example.invalid/widget.js"
        spex-mfg-name="Plugable Technologies"
        spex-mfg-part-number="USBC-TVGA"></script>
      <h1>Plugable USB C to VGA Adapter</h1>
      <div>Sold by <a>Plugable Technologies</a> Top Rated</div>
      <div>Add to cart</div>
    </body></html>
    """
    result = subject.extract_product_page(html)
    assert len(result["products"]) == 1
    product = result["products"][0]
    assert product["name"] == "Plugable USB C to VGA Adapter"
    assert product["mpn"] == "USBC-TVGA"
    assert product["sku"] == "9SIA2XBBKZ0313"
    assert product["price"] == "19.95"
    assert product["brand"] == "Plugable Technologies"
    assert product["seller"] == "Plugable Technologies"
    assert result["organizations"][0]["name"] == "Plugable Technologies"
    assert "$999.99" not in result["visible_text_excerpt"]
    assert "$888.88" not in result["visible_text_excerpt"]


def test_rendered_text_fallback_requires_stable_identifier() -> None:
    html = """
    <html><head><title>Generic Widget</title></head>
    <body><h1>Generic Widget</h1><div>$19.95</div><div>Sold by Vendor Add to cart</div></body></html>
    """
    result = subject.extract_product_page(html)
    assert result["products"] == []



def test_itemprop_text_and_common_b2b_labels_are_vendor_agnostic() -> None:
    html = """
    <html><head><title>USB-C VGA Adapter</title></head><body>
      <h1>USB-C VGA Adapter</h1>
      <span>Mfg # <span itemprop="mpn">USBC-VGA-CABLE</span></span>
      <span>CDW # 7392921</span>
      <div data-price="16.95"></div>
    </body></html>
    """
    result = subject.extract_product_page(html)
    assert result["normalization_status"] == "ready"
    product = result["products"][0]
    assert product["mpn"] == "USBC-VGA-CABLE"
    assert product["price"] == "16.95"


def test_common_model_item_price_labels_normalize_without_vendor_branch() -> None:
    html = """
    <html><head><title>Generic Adapter</title></head><body>
      <h1>Generic Adapter</h1>
      <div>Item #: IM17ZA109 | Model #: USBC-TVGA</div>
      <div>Price is $15.99</div>
    </body></html>
    """
    result = subject.extract_product_page(html)
    product = result["products"][0]
    assert product["mpn"] == "USBC-TVGA"
    assert product["sku"] == "IM17ZA109"
    assert product["price"] == "15.99"


def test_upc_is_secondary_identifier_not_primary_mpn() -> None:
    html = """
    <html><head><title>Generic Adapter</title></head><body>
      <h1>Generic Adapter</h1>
      <div>Product # 34187</div>
      <div>UPC # 889028093702</div>
      <div>$8.99</div>
    </body></html>
    """
    result = subject.extract_product_page(html)
    product = result["products"][0]
    assert product["sku"] == "34187"
    assert product["upc"] == "889028093702"
    assert "mpn" not in product


def test_insufficient_page_marks_richer_acquisition_requirement() -> None:
    html = """
    <html><head><title>Dynamic Product Page</title></head>
    <body><h1>Dynamic Product Page</h1><p>Sign in to see details</p></body></html>
    """
    result = subject.extract_product_page(html)
    assert result["products"] == []
    assert result["normalization_status"] == "needs_richer_acquisition"
    assert result["evidence_mode"] == "none"



def test_duplicate_upc_in_mpn_does_not_override_distinct_sku() -> None:
    html = """
    <html><head><script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "USB-C VGA Adapter",
      "sku": "USBC-TVGA",
      "mpn": "819927012221",
      "gtin12": "819927012221",
      "offers": {"@type": "Offer", "price": "14.95", "priceCurrency": "USD"}
    }
    </script></head><body></body></html>
    """
    result = subject.extract_product_page(html)
    product = result["products"][0]
    assert product["sku"] == "USBC-TVGA"
    assert product["upc"] == "819927012221"
    assert "mpn" not in product
    assert product["identifier_note"] == "source_mpn_duplicated_upc"


def test_invoker_returns_needs_browser_for_simple_http_block(monkeypatch) -> None:
    def blocked(url, max_bytes):
        raise subject.ProcurementWebReadError(
            "product URL returned HTTP 403",
            acquisition_hint="browser_or_api",
            http_status=403,
        )

    monkeypatch.setattr(subject, "_fetch_html", blocked)
    request = SimpleNamespace(
        capability_name=subject.CAPABILITY,
        arguments={"url": "https://vendor.example/item"},
    )
    resolution = SimpleNamespace(selected_provider_id=subject.PROVIDER)

    result = subject.ProcurementWebReadInvoker().invoke(
        request=request,
        resolution=resolution,
    )
    assert result.output["normalization_status"] == "needs_browser_or_api"
    assert result.output["evidence_mode"] == "simple_http_blocked"
    assert result.output["fetch_http_status"] == 403
    assert result.output["products"] == []
