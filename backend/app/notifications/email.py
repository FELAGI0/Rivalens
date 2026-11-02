"""Email notifications: insight summaries via SMTP (aiosmtplib).

All errors are logged and swallowed — email must never break the check
pipeline.
"""

import asyncio
import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

SITE_URL = "https://rivalens.ru"

SMTP_CONNECT_TIMEOUT = 15
SMTP_TOTAL_TIMEOUT = 20


async def _deliver(smtp: aiosmtplib.SMTP, message: EmailMessage) -> None:
    """Connect, login and send inside one SMTP session."""
    async with smtp:
        if settings.smtp_user:
            await smtp.login(settings.smtp_user, settings.smtp_password or "")
        await smtp.send_message(message)


async def send_insight_email(
    to_email: str,
    competitor_name: str,
    summary: str,
    competitor_id: str,
) -> None:
    """Send an HTML email about a new insight.

    No-op when notifications are disabled or SMTP is not configured.
    Raises nothing: failures are logged as warnings.
    """
    if not settings.notifications_enabled:
        return
    if not settings.smtp_host:
        logger.warning("SMTP not configured, skipping email to %s", to_email)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = f"Rivalens: новые изменения у {competitor_name}"
    message.set_content(f"{competitor_name}\n\n{summary}")
    message.add_alternative(
        f"""\
<html>
  <body style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
    <h2 style="margin-bottom: 8px;">{competitor_name}</h2>
    <p style="line-height: 1.5;">{summary}</p>
    <p style="margin-top: 24px;">
      <a href="{SITE_URL}/competitors/{competitor_id}">Открыть детали в Rivalens</a>
    </p>
  </body>
</html>
""",
        subtype="html",
    )

    # Port 465 is implicit TLS: the server expects the TLS handshake as
    # the very first bytes. Port 587 (and 25) is plaintext greeting +
    # STARTTLS upgrade. Choosing the wrong mode makes the server and the
    # client wait for each other forever — hence the connect timeouts
    # observed against smtp.yandex.ru:465.
    implicit_tls = settings.smtp_port == 465

    smtp = aiosmtplib.SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=implicit_tls,
        start_tls=not implicit_tls,
        timeout=SMTP_CONNECT_TIMEOUT,
    )

    try:
        # Belt and suspenders: aiosmtplib timeout covers connect, this
        # covers the whole session (login + send) against a wedged server.
        await asyncio.wait_for(_deliver(smtp, message), timeout=SMTP_TOTAL_TIMEOUT)
        logger.info(
            "insight email sent to %s for competitor %s",
            to_email,
            competitor_name,
        )
    except Exception as e:
        # Deliberately swallowed: the insight is already saved; a broken
        # SMTP server must not fail the pipeline run.
        logger.warning("email send failed: %r", e)
