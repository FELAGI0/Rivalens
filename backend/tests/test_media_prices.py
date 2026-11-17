"""Media-page price suppression tests (CP33)."""

from app.diff.entities import diff_entities
from app.fetcher.extractor import extract_entities


def test_extract_media_prices_ignored() -> None:
    prices = " ".join(f"{1000 + i} ₽" for i in range(12))
    html = f"<html><body><h1>Статьи</h1><p>{prices}</p></body></html>"

    entities = extract_entities(html, url="https://habr.com/ru/")

    assert entities["products"] == []
    assert len(entities["prices"]) == 12
    assert entities["prices_ignored"] is True


def test_extract_media_price_flag_requires_many_prices() -> None:
    html = "<html><body><p>990 ₽ и 1190 ₽</p></body></html>"

    entities = extract_entities(html, url="https://habr.com/ru/")

    assert "prices_ignored" not in entities


def test_diff_ignores_prices_for_media() -> None:
    old = {
        "title": "Habr",
        "headings": ["Старая статья"],
        "links": [{"href": "/old", "text": "Old"}],
        "prices": ["132 000 $", "6800 ₽"],
        "prices_ignored": True,
        "products": [],
    }
    new = {
        "title": "Habr",
        "headings": ["Новая статья"],
        "links": [{"href": "/new", "text": "New"}],
        "prices": ["15 000 ₽", "20 $"],
        "prices_ignored": True,
        "products": [],
    }

    changes = diff_entities(old, new)
    kinds = {change["kind"] for change in changes}

    assert kinds == {"heading_added", "heading_removed", "link_added", "link_removed"}
    assert not {"price_added", "price_removed"} & kinds


def test_diff_normal_prices() -> None:
    old = {
        "title": "Product",
        "headings": [],
        "links": [],
        "prices": ["6800 ₽"],
        "products": [],
    }
    new = {
        "title": "Product",
        "headings": [],
        "links": [],
        "prices": ["20 $"],
        "products": [],
    }

    kinds = {change["kind"] for change in diff_entities(old, new)}

    assert kinds == {"price_added", "price_removed"}


def test_product_prices_are_not_ignored() -> None:
    html = """
    <html><body>
      <article class="product"><h3>A</h3><span class="price">990 ₽</span></article>
      <article class="product"><h3>B</h3><span class="price">1190 ₽</span></article>
      <article class="product"><h3>C</h3><span class="price">1490 ₽</span></article>
      <article class="product"><h3>D</h3><span class="price">1990 ₽</span></article>
      <article class="product"><h3>E</h3><span class="price">2490 ₽</span></article>
      <article class="product"><h3>F</h3><span class="price">2990 ₽</span></article>
    </body></html>
    """

    entities = extract_entities(html, url="https://habr.com/ru/")

    assert len(entities["products"]) == 6
    assert "prices_ignored" not in entities
