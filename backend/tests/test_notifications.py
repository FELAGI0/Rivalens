"""Email notification tests: disabled no-op, send path, pipeline resilience."""

import pytest

from app.config import Settings
from app.config import settings as live_settings
from app.notifications.email import send_insight_email

# Same object, old local name used throughout this module.
settings = live_settings


@pytest.fixture(autouse=True)
def _smtp_settings(monkeypatch):
    # Defaults for every test in this module; individual tests override.
    monkeypatch.setattr(live_settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(live_settings, "smtp_port", 587)
    monkeypatch.setattr(live_settings, "smtp_user", "user@example.com")
    monkeypatch.setattr(live_settings, "smtp_password", "secret")
    monkeypatch.setattr(live_settings, "smtp_from", "noreply@rivalens.ru")
    monkeypatch.setattr(live_settings, "smtp_tls", True)
    monkeypatch.setattr(live_settings, "notifications_enabled", False)


def test_email_default_enabled() -> None:
    """Notifications ship enabled: the core loop of a monitoring product.

    Checked on the Settings class (field default), not on the module-level
    instance — the autouse fixture above patches the instance to False.
    """
    fresh = Settings(
        database_url="x",
        ai_base_url="x",
        ai_api_key="x",
        ai_model="x",
        jwt_secret="x",
    )
    assert fresh.notifications_enabled is True


async def test_email_disabled(monkeypatch) -> None:
    """notifications_enabled=False: no-op, SMTP is never touched."""
    sent = []

    async def fake_send(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr("app.notifications.email.aiosmtplib.send", fake_send)

    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )
    assert sent == []


async def test_email_no_smtp_host(monkeypatch) -> None:
    """Enabled but smtp_host empty: warning logged, nothing sent."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    sent = []

    async def fake_send(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr("app.notifications.email.aiosmtplib.send", fake_send)

    import app.notifications.email as email_mod

    email_mod.settings.smtp_host = ""
    try:
        await send_insight_email(
            "user@example.com", "Competitor A", "summary", "comp-id"
        )
        assert sent == []
    finally:
        email_mod.settings.smtp_host = "smtp.example.com"


async def test_email_sent(monkeypatch) -> None:
    """Enabled + configured: aiosmtplib.send is called with the message."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    captured = {}

    async def fake_send(message, **kwargs):
        captured["message"] = message
        captured["kwargs"] = kwargs

    monkeypatch.setattr("app.notifications.email.aiosmtplib.send", fake_send)

    await send_insight_email(
        "user@example.com", "Competitor A", "prices changed", "comp-id-1"
    )

    message = captured["message"]
    assert message["To"] == "user@example.com"
    assert message["From"] == "noreply@rivalens.ru"
    assert message["Subject"] == "Rivalens: новые изменения у Competitor A"
    plain_part = message.get_body(preferencelist=("plain",))
    assert plain_part is not None
    assert "prices changed" in plain_part.get_content()
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    assert "prices changed" in html_part.get_content()
    assert "/competitors/comp-id-1" in html_part.get_content()

    kwargs = captured["kwargs"]
    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert kwargs["start_tls"] is True


async def test_email_send_error_is_swallowed(monkeypatch) -> None:
    """A failing SMTP server raises nothing: the error is only logged."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    async def failing_send(*args, **kwargs):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(
        "app.notifications.email.aiosmtplib.send", failing_send
    )

    # Must not raise.
    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )


async def test_pipeline_email_error_does_not_break(
    db, fake_fetch, monkeypatch
) -> None:
    """Full pipeline: insights are saved even when email blowing up."""
    from sqlalchemy import select

    from app.models import Insight
    from app.pipeline import run_competitor_check
    from tests.test_pipeline import (  # noqa: F401 — reuse helpers
        HTML_V1,
        HTML_V2,
        PAGE_URL,
        _make_competitor_with_page,
        _mock_llm_success,
    )

    _mock_llm_success(monkeypatch)
    page = _make_competitor_with_page(db)

    # Notifications on, SMTP broken.
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

    async def failing_send(*args, **kwargs):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(
        "app.notifications.email.aiosmtplib.send", failing_send
    )

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)
    fake_fetch.route(PAGE_URL, html=HTML_V2)
    result = await run_competitor_check(page.competitor_id, db)

    assert result["insight_id"] is not None
    insights = db.scalars(
        select(Insight).where(Insight.competitor_id == page.competitor_id)
    ).all()
    assert len(insights) == 1


async def test_pipeline_sends_email_on_insight(
    db, fake_fetch, monkeypatch
) -> None:
    """Full pipeline: a created insight triggers exactly one email."""
    from app.pipeline import run_competitor_check
    from tests.test_pipeline import (  # noqa: F401 — reuse helpers
        HTML_V1,
        HTML_V2,
        PAGE_URL,
        _make_competitor_with_page,
        _mock_llm_success,
    )

    _mock_llm_success(monkeypatch)
    page = _make_competitor_with_page(db)

    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

    sent = []

    async def fake_send(message, **kwargs):
        sent.append(message)

    monkeypatch.setattr("app.notifications.email.aiosmtplib.send", fake_send)

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)
    # First check: no changes, no insight, no email.
    assert sent == []

    fake_fetch.route(PAGE_URL, html=HTML_V2)
    result = await run_competitor_check(page.competitor_id, db)

    assert result["insight_id"] is not None
    assert len(sent) == 1
    assert sent[0]["Subject"] == "Rivalens: новые изменения у Competitor A"


async def test_email_skipped_when_smtp_empty(monkeypatch, caplog) -> None:
    """Enabled + empty smtp_host: no send, warning logged, no raise."""
    import logging

    monkeypatch.setattr(settings, "notifications_enabled", True)

    sent = []

    async def fake_send(*args, **kwargs):
        sent.append((args, kwargs))

    monkeypatch.setattr("app.notifications.email.aiosmtplib.send", fake_send)

    import app.notifications.email as email_mod

    previous_host = email_mod.settings.smtp_host
    email_mod.settings.smtp_host = ""
    try:
        with caplog.at_level(logging.WARNING, logger="app.notifications.email"):
            await send_insight_email(
                "user@example.com", "Competitor A", "summary", "comp-id"
            )
        assert sent == []
        assert any(
            "SMTP not configured" in r.message for r in caplog.records
        ), [r.message for r in caplog.records]
    finally:
        email_mod.settings.smtp_host = previous_host
