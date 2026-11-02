"""Billing tests: plan info, free-plan limit, plan upgrade, YooKassa."""

import httpx
import pytest

from app.billing.limits import plan_name
from app.db.session import get_session
from app.main import app
from app.models import User
from tests.conftest import make_user


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)


async def _auth_header(db, user) -> str:
    from app.auth.security import create_access_token

    return f"Bearer {create_access_token(str(user.id))}"


async def _add_competitor(client, headers, name: str, url: str) -> httpx.Response:
    return await client.post(
        "/api/v1/competitors",
        json={"name": name, "url": url},
        headers=headers,
    )


async def test_plan_default_free(client, db) -> None:
    user = make_user(db, "free@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    response = await client.get("/api/v1/billing/plan", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["competitors_limit"] == 2
    assert body["competitors_used"] == 0


async def test_free_limit_blocks_third(client, db) -> None:
    """free=2: two competitors fit, the third is blocked with 402."""
    user = make_user(db, "free-limit@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    for name, host in (
        ("First", "first.example.com"),
        ("Second", "second.example.com"),
    ):
        response = await _add_competitor(
            client, headers, name, f"https://{host}"
        )
        assert response.status_code == 201

    response = await _add_competitor(
        client, headers, "Third", "https://third.example.com"
    )
    assert response.status_code == 402
    assert "Pro" in response.json()["detail"]


async def test_upgrade_unlocks(client, db) -> None:
    user = make_user(db, "upgrade@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    first = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert first.status_code == 201

    # Upgrade to pro, then fill past the free limit of 2.
    response = await client.post(
        "/api/v1/billing/plan", json={"plan": "pro"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"
    assert response.json()["competitors_limit"] == 10

    for name, host in (
        ("Second", "second.example.com"),
        ("Third", "third.example.com"),
        ("Fourth", "fourth.example.com"),
    ):
        response = await _add_competitor(
            client, headers, name, f"https://{host}"
        )
        assert response.status_code == 201


async def test_get_plan_shows_used(client, db) -> None:
    user = make_user(db, "used@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    response = await _add_competitor(
        client, headers, "Only one", "https://only.example.com"
    )
    assert response.status_code == 201

    response = await client.get("/api/v1/billing/plan", headers=headers)
    assert response.status_code == 200
    assert response.json()["competitors_used"] == 1


async def test_free_limit_two(client, db) -> None:
    """Free plan now fits 2 competitors; the third is a 402."""
    user = make_user(db, "free-two@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    first = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert first.status_code == 201

    second = await _add_competitor(
        client, headers, "Second", "https://second.example.com"
    )
    assert second.status_code == 201

    third = await _add_competitor(
        client, headers, "Third", "https://third.example.com"
    )
    assert third.status_code == 402
    assert "Pro" in third.json()["detail"]


# --- CP14/CP15: YooKassa checkout + webhook ---


def _webhook_body(
    user_id: str,
    plan: str = "pro",
    event: str = "payment.succeeded",
    metadata: dict | None = None,
) -> dict:
    return {
        "type": "notification",
        "event": event,
        "object": {
            "id": "payment-1",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "900.00", "currency": "RUB"},
            "metadata": metadata
            if metadata is not None
            else {"user_id": str(user_id), "plan": plan},
        },
    }


def _mock_verify(
    monkeypatch, user_id: str, plan: str = "pro", status: str = "succeeded"
) -> None:
    """Patch billing.verify_payment: return payment matching the webhook."""
    from app.billing.yookassa import YooKassaError

    async def fake_verify(payment_id: str) -> dict:
        if status == "__error__":
            raise YooKassaError(f"payment {payment_id} not found")
        return {
            "id": payment_id,
            "status": status,
            "metadata": {"user_id": str(user_id), "plan": plan},
        }

    monkeypatch.setattr("app.api.billing.verify_payment", fake_verify)


async def test_create_payment_mock(client, db, monkeypatch) -> None:
    """checkout: mocked YooKassa API -> confirmation_url returned to frontend."""
    user = make_user(db, "checkout@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    captured = {}

    async def fake_create_payment(user_id, plan, amount_rub):
        captured["user_id"] = user_id
        captured["plan"] = plan
        captured["amount_rub"] = amount_rub
        return {
            "payment_id": "payment-1",
            "confirmation_url": "https://yoomoney.ru/checkout/payments/v2/contract?orderId=payment-1",
        }

    monkeypatch.setattr("app.api.billing.create_payment", fake_create_payment)

    response = await client.post(
        "/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers
    )
    assert response.status_code == 200
    assert "confirmation_url" in response.json()

    assert captured["plan"] == "pro"
    assert captured["amount_rub"] == 900
    assert captured["user_id"] == str(user.id)


async def test_checkout_requires_auth(client, db) -> None:
    response = await client.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 401


async def test_webhook_succeeded(client, db, monkeypatch) -> None:
    """payment.succeeded webhook activates the plan, no auth needed."""
    user = make_user(db, "webhook@example.com")
    _mock_verify(monkeypatch, user.id)

    response = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert response.status_code == 200

    db.refresh(user)
    assert plan_name(user.plan) == "pro"

    fresh = db.get(User, user.id)
    assert plan_name(fresh.plan) == "pro"


async def test_webhook_ignored_for_other_events(client, db, monkeypatch) -> None:
    """Anything that is not payment.succeeded: 200 OK, plan unchanged."""
    user = make_user(db, "other-event@example.com")
    _mock_verify(monkeypatch, user.id)

    response = await client.post(
        "/api/v1/billing/webhook",
        json=_webhook_body(user.id, event="payment.canceled"),
    )
    assert response.status_code == 200

    db.refresh(user)
    assert plan_name(user.plan) == "free"


async def test_webhook_idempotent(client, db, monkeypatch) -> None:
    """Repeated webhook: still 200, plan still pro, no error."""
    user = make_user(db, "idempotent@example.com")
    _mock_verify(monkeypatch, user.id)

    first = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert first.status_code == 200
    db.refresh(user)
    assert plan_name(user.plan) == "pro"

    second = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert second.status_code == 200
    db.refresh(user)
    assert plan_name(user.plan) == "pro"


# --- CP15: webhook security (verify via YooKassa API) ---


async def test_webhook_verifies_payment(client, db, monkeypatch) -> None:
    """Verified succeeded payment: plan changes."""
    user = make_user(db, "verify-ok@example.com")
    _mock_verify(monkeypatch, user.id)

    response = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert response.status_code == 200

    db.refresh(user)
    assert plan_name(user.plan) == "pro"


async def test_webhook_rejects_fake_payment(client, db, monkeypatch) -> None:
    """Notification claims success, API says canceled: plan NOT changed."""
    user = make_user(db, "fake-payment@example.com")
    # Verification returns status=canceled for this payment.
    _mock_verify(monkeypatch, user.id, status="canceled")

    response = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert response.status_code == 200

    db.refresh(user)
    assert plan_name(user.plan) == "free"


async def test_webhook_rejects_metadata_mismatch(
    client, db, monkeypatch
) -> None:
    """Webhook metadata disagrees with the API's: plan NOT changed."""
    attacker_target = make_user(db, "victim@example.com")
    # API truth: the payment belongs to a different user.
    _mock_verify(monkeypatch, attacker_target.id, plan="pro")
    # Webhook body: forged metadata points at another user.
    other_user = make_user(db, "other-victim@example.com")

    response = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(other_user.id)
    )
    assert response.status_code == 200

    db.refresh(other_user)
    db.refresh(attacker_target)
    # Neither user got the plan.
    assert plan_name(other_user.plan) == "free"
    assert plan_name(attacker_target.plan) == "free"


async def test_webhook_verification_error_is_500(
    client, db, monkeypatch
) -> None:
    """YooKassa API unreachable: 500 so YooKassa retries the webhook."""
    user = make_user(db, "retry@example.com")
    _mock_verify(monkeypatch, user.id, status="__error__")

    response = await client.post(
        "/api/v1/billing/webhook", json=_webhook_body(user.id)
    )
    assert response.status_code == 500

    db.refresh(user)
    assert plan_name(user.plan) == "free"
