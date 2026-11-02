"""YooKassa hosted checkout: create payments via the REST API.

https://yookassa.ru/developers/api — POST /v3/payments with Basic
auth (shopId:secretKey) and an Idempotence-Key header. Webhook
notifications are verified by re-fetching the payment via
GET /v3/payments/{id} — YooKassa does not sign notifications.
"""

import logging
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3/payments"
TIMEOUT_SECONDS = 10


class YooKassaError(Exception):
    """Raised when payment creation fails (API error, missing creds)."""


async def create_payment(user_id: str, plan: str, amount_rub: int) -> dict:
    """Create a redirect payment; return payment id and confirmation URL.

    Raises YooKassaError on any failure — callers translate that into an
    HTTP 502 so the user sees "payment unavailable" instead of a stack trace.
    """
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise YooKassaError("YooKassa credentials are not configured")

    payload = {
        "amount": {"value": f"{amount_rub:.0f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url,
        },
        "description": f"Rivalens {plan}",
        "metadata": {"user_id": str(user_id), "plan": plan},
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(
            YOOKASSA_API_BASE,
            auth=(
                settings.yookassa_shop_id,
                settings.yookassa_secret_key,
            ),
            headers={"Idempotence-Key": str(uuid.uuid4())},
        )

    if response.status_code != 200:
        logger.warning(
            "YooKassa payment creation failed: HTTP %s %s",
            response.status_code,
            response.text[:500],
        )
        raise YooKassaError("payment creation failed")

    payment = response.json()
    confirmation_url = None
    confirmation = payment.get("confirmation") or {}
    if confirmation.get("type") == "redirect":
        confirmation_url = confirmation.get("confirmation_url")

    if not confirmation_url:
        raise YooKassaError("no confirmation_url in YooKassa response")

    return {
        "payment_id": payment["id"],
        "confirmation_url": confirmation_url,
    }


async def verify_payment(payment_id: str) -> dict:
    """Fetch the payment object from YooKassa by id.

    The source of truth for the webhook: notifications from YooKassa are
    not signed, so before activating a plan we re-read the payment via
    the API and trust only that response (status, metadata, amount).
    """
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise YooKassaError("YooKassa credentials are not configured")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{YOOKASSA_API_BASE}/{payment_id}",
            auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
        )

    if response.status_code != 200:
        logger.warning(
            "YooKassa payment verification failed: HTTP %s %s",
            response.status_code,
            response.text[:500],
        )
        raise YooKassaError(f"payment {payment_id} not found")

    return response.json()
