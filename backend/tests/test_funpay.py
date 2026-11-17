"""FunPay parser integration tests (CP32)."""

from pathlib import Path

import pytest

from app.fetcher import extractor
from app.fetcher.extractor import extract_entities

FIXTURE = Path(__file__).parent / "fixtures" / "funpay_lots.html"
FUNPAY_URL = "https://funpay.com/lots/4234/"


def test_extract_funpay_products() -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    entities = extract_entities(html, url=FUNPAY_URL)

    assert len(entities["products"]) > 0
    assert entities["prices"] == []
    for product in entities["products"]:
        assert product["title"]
        assert product["price"]
        assert product["url"].startswith("https://funpay.com/lots/offer?id=")


def test_extract_funpay_products_are_limited() -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    entities = extract_entities(html, url=FUNPAY_URL)

    assert len(entities["products"]) == 50


def test_extract_funpay_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html><head><title>FunPay fallback</title></head>
    <body><h1>Лоты</h1><p>Цена 5410 ₽</p></body></html>
    """

    def broken_parser(_: str) -> list[dict]:
        raise RuntimeError("parser failed")

    monkeypatch.setattr(extractor, "_funpay_products", broken_parser)

    entities = extract_entities(html, url=FUNPAY_URL)

    assert entities["products"] == []
    assert entities["prices"] == ["5410 ₽"]
