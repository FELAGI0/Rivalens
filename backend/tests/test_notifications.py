"""Email notification tests: disabled no-op, send path, pipeline resilience.

SMTP is mocked at the class level: aiosmtplib.SMTP is replaced by
FakeSMTP which records constructor args, login and sent messages.
"""

import logging

import pytest

from app.config import Settings
from app.config import settings as live_settings
from app.notifications.email import send_digest_email, send_insight_email

# Same object, old local name used throughout this module.
settings = live_settings


class FakeSMTP:
    """Records how email.py drives an SMTP session."""

    instances: list["FakeSMTP"] = []

    def __init__(
        self,
        hostname: str,
        port: int,
        use_tls: bool,
        start_tls: bool,
        timeout: float | None,
    ) -> None:
        self.hostname = hostname
        self.port = port
        self.use_tls = use_tls
        self.start_tls = start_tls
        self.timeout = timeout
        self.logged_in: tuple[str, str] | None = None
        self.sent_messages: list = []
        self.fail_on: Exception | None = None
        FakeSMTP.instances.append(self)

    async def __aenter__(self) -> "FakeSMTP":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    async def send_message(self, message) -> None:
        if self.fail_on is not None:
            raise self.fail_on
        self.sent_messages.append(message)

    @classmethod
    def sent(cls) -> list:
        """All messages sent across all instances."""
        return [m for inst in cls.instances for m in inst.sent_messages]


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


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch):
    """Replace aiosmtplib.SMTP with FakeSMTP, reset per test."""
    import aiosmtplib

    FakeSMTP.instances = []
    monkeypatch.setattr(aiosmtplib, "SMTP", FakeSMTP)
    return FakeSMTP


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


async def test_email_disabled() -> None:
    """notifications_enabled=False (fixture default): SMTP never touched."""
    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )
    assert FakeSMTP.instances == []


async def test_email_no_smtp_host(monkeypatch) -> None:
    """Enabled but smtp_host empty: warning logged, nothing sent."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    import app.notifications.email as email_mod

    previous_host = email_mod.settings.smtp_host
    email_mod.settings.smtp_host = ""
    try:
        await send_insight_email(
            "user@example.com", "Competitor A", "summary", "comp-id"
        )
        assert FakeSMTP.instances == []
    finally:
        email_mod.settings.smtp_host = previous_host


async def test_email_sent(monkeypatch) -> None:
    """Enabled + configured: SMTP is driven with the message."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    await send_insight_email(
        "user@example.com", "Competitor A", "prices changed", "comp-id-1"
    )

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]

    message = smtp.sent_messages[0]
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

    # Credentials are used via login, not constructor args.
    assert smtp.logged_in == ("user@example.com", "secret")


async def test_email_smtp_587_uses_starttls(monkeypatch) -> None:
    """Port 587: plaintext connect + STARTTLS upgrade."""
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_port", 587)

    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )

    smtp = FakeSMTP.instances[0]
    assert smtp.use_tls is False
    assert smtp.start_tls is True
    assert smtp.timeout is not None


async def test_email_smtp_465_uses_implicit_tls(monkeypatch) -> None:
    """Port 465: implicit TLS handshake from the first byte.

    Regression test for the connect timeout against smtp.yandex.ru:465 —
    the server waits for a TLS handshake while a STARTTLS client waits
    for a plaintext "220 ready".
    """
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_port", 465)

    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )

    smtp = FakeSMTP.instances[0]
    assert smtp.use_tls is True
    assert smtp.start_tls is False
    assert smtp.timeout is not None


async def test_email_send_error_is_swallowed(monkeypatch) -> None:
    """A failing SMTP server raises nothing: the error is only logged."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    # Make every instance fail on send_message.
    original_init = FakeSMTP.__init__

    def failing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.fail_on = ConnectionRefusedError("smtp down")

    monkeypatch.setattr(FakeSMTP, "__init__", failing_init)

    # Must not raise.
    await send_insight_email(
        "user@example.com", "Competitor A", "summary", "comp-id"
    )
    assert FakeSMTP.sent() == []


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

    # Notifications on, SMTP broken. Instant mode: email right in the
    # pipeline (digest mode defers to the weekly job).
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "email_mode", "instant")

    original_init = FakeSMTP.__init__

    def failing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.fail_on = ConnectionRefusedError("smtp down")

    FakeSMTP.__init__ = failing_init  # noqa: monkeypatch below covers reset
    try:
        fake_fetch.route(PAGE_URL, html=HTML_V1)
        await run_competitor_check(page.competitor_id, db)
        fake_fetch.route(PAGE_URL, html=HTML_V2)
        result = await run_competitor_check(page.competitor_id, db)
    finally:
        FakeSMTP.__init__ = original_init

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
    monkeypatch.setattr(settings, "email_mode", "instant")

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)
    # First check: no changes, no insight, no email.
    assert FakeSMTP.sent() == []

    fake_fetch.route(PAGE_URL, html=HTML_V2)
    result = await run_competitor_check(page.competitor_id, db)

    assert result["insight_id"] is not None
    assert len(FakeSMTP.sent()) == 1
    assert FakeSMTP.sent()[0]["Subject"] == (
        "Rivalens: новые изменения у Competitor A"
    )


async def test_email_skipped_when_smtp_empty(monkeypatch, caplog) -> None:
    """Enabled + empty smtp_host: no send, warning logged, no raise."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    import app.notifications.email as email_mod

    previous_host = email_mod.settings.smtp_host
    email_mod.settings.smtp_host = ""
    try:
        with caplog.at_level(
            logging.WARNING, logger="app.notifications.email"
        ):
            await send_insight_email(
                "user@example.com", "Competitor A", "summary", "comp-id"
            )
        assert FakeSMTP.instances == []
        assert any(
            "SMTP not configured" in r.message for r in caplog.records
        ), [r.message for r in caplog.records]
    finally:
        email_mod.settings.smtp_host = previous_host


# --- CP18: weekly digest ---


async def test_digest_email_sent(monkeypatch) -> None:
    """Digest: one email, all items in the body, links to competitors."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    items = [
        {
            "competitor_name": "Competitor A",
            "summary": "summary A",
            "competitor_id": "comp-a",
        },
        {
            "competitor_name": "Competitor B",
            "summary": "summary B",
            "competitor_id": "comp-b",
        },
    ]

    await send_digest_email("user@example.com", items)

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert len(smtp.sent_messages) == 1

    message = smtp.sent_messages[0]
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Rivalens: дайджест за неделю (2 изменений)"

    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    html = html_part.get_content()
    assert "Дайджест за неделю" in html
    assert "Competitor A" in html
    assert "Competitor B" in html
    assert "summary A" in html
    assert "summary B" in html
    assert "/competitors/comp-a" in html
    assert "/competitors/comp-b" in html


async def test_digest_skipped_when_empty(monkeypatch) -> None:
    """No insights this week: nothing sent at all."""
    monkeypatch.setattr(settings, "notifications_enabled", True)

    await send_digest_email("user@example.com", [])

    assert FakeSMTP.instances == []


async def test_digest_skipped_when_disabled() -> None:
    """notifications_enabled=False (fixture default): no SMTP touched."""
    await send_digest_email("user@example.com", [{"x": 1}])
    assert FakeSMTP.instances == []


async def test_pipeline_instant_mode_sends_email(
    db, fake_fetch, monkeypatch
) -> None:
    """email_mode=instant: send_insight_email runs inside the pipeline."""
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
    monkeypatch.setattr(settings, "email_mode", "instant")

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)
    fake_fetch.route(PAGE_URL, html=HTML_V2)
    result = await run_competitor_check(page.competitor_id, db)

    assert result["insight_id"] is not None
    assert len(FakeSMTP.sent()) == 1


async def test_pipeline_digest_mode_does_not_send_immediately(
    db, fake_fetch, monkeypatch
) -> None:
    """email_mode=digest: no email now, insight persisted for Monday."""
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

    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "email_mode", "digest")

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)
    fake_fetch.route(PAGE_URL, html=HTML_V2)
    result = await run_competitor_check(page.competitor_id, db)

    assert result["insight_id"] is not None
    # No email — the digest job will collect it later.
    assert FakeSMTP.sent() == []
    insights = db.scalars(
        select(Insight).where(Insight.competitor_id == page.competitor_id)
    ).all()
    assert len(insights) == 1
