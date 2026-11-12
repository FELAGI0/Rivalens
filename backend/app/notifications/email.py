"""Email notifications: insight summaries via SMTP (aiosmtplib).

All errors are logged and swallowed — email must never break the check
pipeline.
"""

import asyncio
import html
import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

SITE_URL = "https://rivalens.ru"

SMTP_CONNECT_TIMEOUT = 15
SMTP_TOTAL_TIMEOUT = 20

# Link colour: the site's coral #E85D3D is 3.3:1 on white, below AA for
# body-sized links. The darker coral keeps the brand and clears 5.1:1.
LINK_COLOR = "#C24228"
BODY_COLOR = "#1A1A1A"
MUTED_COLOR = "#6B6B66"


def _pluralize_changes(n: int) -> str:
    """Russian plural form of «изменение» for a count.

    1, 21, 31 → изменение; 2-4, 22-24 → изменения; 0, 5-20, 11-14 → изменений.
    """
    if n % 10 == 1 and n % 100 != 11:
        return "изменение"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "изменения"
    return "изменений"


def _shell(title: str, body_html: str) -> str:
    """HTML document shell shared by the insight and digest emails.

    No external CSS: email clients strip it. Inline styles only, system
    font stacks, and a footer on every message (recipients need a way
    out and a way to change frequency).
    """
    return f"""\
<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(title)}</title>
  </head>
  <body style="margin: 0; padding: 0; background-color: #FAFAF8;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background-color: #FAFAF8;">
      <tr>
        <td align="center" style="padding: 32px 16px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width: 480px; background-color: #FFFFFF;
                        border: 1px solid #E3E2DC;">
            <tr>
              <td style="padding: 28px 24px;
                         font-family: Georgia, 'Times New Roman', serif;
                         font-size: 20px; font-weight: 600; color: {BODY_COLOR};">
                Rivalens
              </td>
            </tr>
            <tr>
              <td style="padding: 0 24px 28px;
                         font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
                         font-size: 15px; line-height: 1.55; color: {BODY_COLOR};">
                {body_html}
              </td>
            </tr>
          </table>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width: 480px;">
            <tr>
              <td style="padding: 20px 8px 0;
                         font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
                         font-size: 12px; line-height: 1.6; color: {MUTED_COLOR};">
                <p style="margin: 0 0 8px;">
                  Вы получаете это письмо, потому что отслеживаете конкурентов
                  на <a href="{SITE_URL}" style="color: {LINK_COLOR};">rivalens.ru</a>.
                </p>
                <p style="margin: 0;">
                  <a href="{SITE_URL}/billing" style="color: {LINK_COLOR};">Настроить частоту писем</a>
                  &nbsp;·&nbsp;
                  <a href="{SITE_URL}/billing" style="color: {LINK_COLOR};">Отписаться</a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def _link(text: str, href: str) -> str:
    return f'<a href="{html.escape(href, quote=True)}" style="color: {LINK_COLOR};">{html.escape(text)}</a>'


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
    body_html = f"""\
        <h1 style="margin: 0 0 8px; font-family: Georgia, 'Times New Roman', serif;
                   font-size: 22px; font-weight: 600; color: {BODY_COLOR};">
          {html.escape(competitor_name)}
        </h1>
        <p style="margin: 0 0 20px;">{html.escape(summary)}</p>
        <p style="margin: 0;">
          {_link("Открыть детали в Rivalens", f"{SITE_URL}/competitors/{competitor_id}")}
        </p>"""
    message.add_alternative(
        _shell(f"Rivalens: новые изменения у {competitor_name}", body_html),
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


async def send_digest_email(
    to_email: str,
    items: list[dict],
) -> None:
    """Send the weekly digest: one email with all insights of the week.

    items: [{competitor_name, summary, competitor_id}]. An empty list
    sends nothing. Errors are logged and swallowed, like everywhere
    in notifications.
    """
    if not settings.notifications_enabled:
        return
    if not settings.smtp_host:
        logger.warning("SMTP not configured, skipping digest to %s", to_email)
        return
    if not items:
        return

    parts: list[str] = []
    for i, item in enumerate(items):
        border = "border-top: 1px solid #E3E2DC; padding-top: 20px; margin-top: 20px;" if i > 0 else ""
        parts.append(
            f"""
        <div style="{border}">
          <h2 style="margin: 0 0 8px; font-family: Georgia, 'Times New Roman', serif;
                     font-size: 18px; font-weight: 600; color: {BODY_COLOR};">
            {html.escape(str(item["competitor_name"]))}
          </h2>
          <p style="margin: 0 0 8px;">{html.escape(str(item["summary"]))}</p>
          <p style="margin: 0;">
            {_link("Открыть →", f"{SITE_URL}/competitors/{item['competitor_id']}")}
          </p>
        </div>"""
        )

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = (
        f"Rivalens: дайджест за неделю ({len(items)} {_pluralize_changes(len(items))})"
    )
    message.set_content(
        "\n\n".join(
            f'{item["competitor_name"]}\n{item["summary"]}\n'
            f"{SITE_URL}/competitors/{item['competitor_id']}"
            for item in items
        )
    )
    body_html = (
        f'<h1 style="margin: 0 0 20px; font-family: Georgia, \'Times New Roman\', serif;'
        f' font-size: 22px; font-weight: 600; color: {BODY_COLOR};">Дайджест за неделю</h1>'
        + "".join(parts)
    )
    message.add_alternative(
        _shell("Rivalens: дайджест за неделю", body_html),
        subtype="html",
    )

    implicit_tls = settings.smtp_port == 465
    smtp = aiosmtplib.SMTP(
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=implicit_tls,
        start_tls=not implicit_tls,
        timeout=SMTP_CONNECT_TIMEOUT,
    )

    try:
        await asyncio.wait_for(_deliver(smtp, message), timeout=SMTP_TOTAL_TIMEOUT)
        logger.info("digest email sent to %s (%d items)", to_email, len(items))
    except Exception as e:
        logger.warning("digest email send failed: %r", e)
