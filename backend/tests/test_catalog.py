"""Catalog parsing (CP31): product extraction and product-level diff."""

from app.diff.entities import diff_entities, diff_products
from app.fetcher.extractor import extract_entities


def _jsonld_html(products_json: str) -> str:
    return f"""
    <html>
      <head>
        <title>Каталог ОЗУ</title>
        <script type="application/ld+json">
          {products_json}
        </script>
      </head>
      <body><h1>Оперативная память</h1></body>
    </html>
    """


def test_extract_products_jsonld() -> None:
    html = _jsonld_html(
        """
        [
          {
            "@type": "Product",
            "name": "Kingston Fury 16GB",
            "url": "https://shop.example/kf16",
            "offers": {"@type": "Offer", "price": "6350", "priceCurrency": "RUB"}
          },
          {
            "@type": "Product",
            "name": "Samsung DDR5 32GB",
            "url": "https://shop.example/sd32",
            "offers": {"@type": "Offer", "price": 127000, "priceCurrency": "RUB"}
          }
        ]
        """
    )

    entities = extract_entities(html)

    products = entities["products"]
    assert len(products) == 2
    assert products[0] == {
        "title": "Kingston Fury 16GB",
        "price": "6350 ₽",
        "url": "https://shop.example/kf16",
    }
    assert products[1]["title"] == "Samsung DDR5 32GB"
    assert "127000" in products[1]["price"]


def test_extract_products_jsonld_graph_and_broken_json() -> None:
    """@graph nodes are read; a malformed script block is skipped, not fatal."""
    html = """
    <html><head>
      <script type="application/ld+json">{not json}</script>
      <script type="application/ld+json">
      {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": "page"},
        {"@type": "Product", "name": "Only product",
         "offers": {"price": "1990", "priceCurrency": "RUB"}}
      ]}
      </script>
    </head><body></body></html>
    """

    products = extract_entities(html)["products"]

    assert len(products) == 1
    assert products[0]["title"] == "Only product"
    assert products[0]["price"] == "1990 ₽"


def test_extract_products_fallback() -> None:
    card = """
    <article class="product">
      <a href="{url}"><h3 class="product-title">{title}</h3></a>
      <span class="price">{price} ₽</span>
    </article>
    """
    cards = "".join(
        card.format(url=f"https://shop.example/{i}", title=f"Товар {i}", price=price)
        for i, price in enumerate(["1 990", "2 490", "3 990", "4 990"])
    )
    html = f"<html><body><main>{cards}</main></body></html>"

    products = extract_entities(html)["products"]

    assert len(products) == 4
    assert products[0]["title"] == "Товар 0"
    assert products[0]["url"] == "https://shop.example/0"
    assert products[0]["price"] == "1 990 ₽"


def test_single_product_page_has_no_products() -> None:
    """Two cards is not a catalog: page-level `prices` stays the signal."""
    html = """
    <html><body>
      <article class="product"><h3>Item A</h3><span class="price">990 ₽</span></article>
      <article class="product"><h3>Item B</h3><span class="price">1490 ₽</span></article>
    </body></html>
    """

    entities = extract_entities(html)

    assert entities["products"] == []
    assert "990 ₽" in entities["prices"]


def test_extract_products_limit() -> None:
    cards = "".join(
        f'<div class="product-card"><h3>P{i}</h3>'
        f'<span class="price">{1000 + i} ₽</span></div>'
        for i in range(80)
    )
    html = f"<html><body>{cards}</body></html>"

    products = extract_entities(html)["products"]

    assert len(products) == 50


def _snapshot(products: list[dict]) -> dict:
    return {
        "title": "Каталог",
        "headings": [],
        "links": [],
        "prices": ["6350 ₽", "127000 ₽"],
        "products": products,
    }


def test_diff_products_price_changed() -> None:
    old = _snapshot(
        [
            {"title": "Kingston Fury 16GB", "price": "6350 ₽", "url": "/kf16"},
            {"title": "Samsung DDR5 32GB", "price": "127000 ₽", "url": "/sd32"},
        ]
    )
    new = _snapshot(
        [
            {"title": "Kingston Fury 16GB", "price": "5990 ₽", "url": "/kf16"},
            {"title": "Samsung DDR5 32GB", "price": "127000 ₽", "url": "/sd32"},
        ]
    )

    changes = diff_entities(old, new)

    product_changes = [c for c in changes if c["kind"].startswith("product_")]
    assert product_changes == [
        {
            "kind": "product_price_changed",
            "payload": {
                "title": "Kingston Fury 16GB",
                "from": "6350 ₽",
                "to": "5990 ₽",
                "url": "/kf16",
            },
        }
    ]
    # The page-level price set must NOT be diffed when products exist.
    assert not [c for c in changes if c["kind"].startswith("price_")]


def test_diff_products_added_removed() -> None:
    old = _snapshot(
        [
            {"title": "Kingston Fury 16GB", "price": "6350 ₽", "url": "/kf16"},
            {"title": "Samsung DDR5 32GB", "price": "127000 ₽", "url": "/sd32"},
        ]
    )
    new = _snapshot(
        [
            {"title": "Kingston Fury 16GB", "price": "6350 ₽", "url": "/kf16"},
            {"title": "Crucial 8GB", "price": "2990 ₽", "url": "/cr8"},
        ]
    )

    kinds_and_titles = {
        (c["kind"], c["payload"]["title"]) for c in diff_products(old, new)
    }

    assert ("product_removed", "Samsung DDR5 32GB") in kinds_and_titles
    assert ("product_added", "Crucial 8GB") in kinds_and_titles
    assert ("product_price_changed", "Kingston Fury 16GB") not in kinds_and_titles


def test_diff_products_falls_back_to_title_key() -> None:
    """Cards without links are matched by title."""
    old = _snapshot([{"title": "Kingston Fury 16GB", "price": "6350 ₽", "url": ""}])
    new = _snapshot([{"title": "Kingston Fury 16GB", "price": "5990 ₽", "url": ""}])

    changes = diff_products(old, new)

    assert len(changes) == 1
    assert changes[0]["kind"] == "product_price_changed"


def test_diff_without_products_keeps_price_set_logic() -> None:
    """Single-product pages keep the old price_added/price_removed behavior."""
    old = {
        "title": "Базовый",
        "headings": [],
        "links": [],
        "prices": ["990 ₽"],
        "products": [],
    }
    new = {
        "title": "Базовый",
        "headings": [],
        "links": [],
        "prices": ["1190 ₽"],
        "products": [],
    }

    kinds = {c["kind"] for c in diff_entities(old, new)}

    assert kinds == {"price_added", "price_removed"}
