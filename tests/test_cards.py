from decimal import Decimal


def register(client):
    return client.post(
        "/api/auth/register",
        json={"email": "card@example.com", "password": "correct horse", "display_name": "Card User"},
    ).json()["csrf_token"]


def account(client, csrf, name="Cuenta COP", currency="COP"):
    return client.post(
        "/api/accounts",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": name,
            "account_type": "checking",
            "currency": currency,
            "opening_balance": "2000000" if currency == "COP" else "0",
            "opening_balance_date": "2026-01-01",
        },
    ).json()


def test_card_purchase_debt_installments_and_payment(client):
    csrf = register(client)
    source = account(client, csrf)
    categories = client.get("/api/categories").json()
    food = next(item for item in categories if item["name"] == "Alimentación")
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Visa Principal",
            "statement_closing_day": 15,
            "currencies": [{"currency": "COP", "credit_limit": "3000000"}, {"currency": "USD"}],
        },
    )
    assert card.status_code == 201, card.text
    card_id = card.json()["id"]
    rate = client.post(
        f"/api/cards/{card_id}/interest-rates",
        headers={"X-CSRF-Token": csrf},
        json={"currency": "COP", "monthly_rate": "0.02", "effective_from": "2026-01-01"},
    )
    assert rate.status_code == 201, rate.text
    precise_rate = client.post(
        f"/api/cards/{card_id}/interest-rates",
        headers={"X-CSRF-Token": csrf},
        json={"currency": "COP", "monthly_rate": "0.021234567891", "effective_from": "2027-01-01"},
    )
    assert precise_rate.status_code == 201, precise_rate.text
    assert Decimal(precise_rate.json()["monthly_rate"]) == Decimal("0.021234567891")

    purchase = client.post(
        f"/api/cards/{card_id}/purchases",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "purchase-1"},
        json={
            "card_id": card_id,
            "category_id": food["id"],
            "amount": "1000000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 5,
            "description": "Computador",
        },
    )
    assert purchase.status_code == 201, purchase.text
    assert len(purchase.json()["installments"]) == 5
    assert Decimal(purchase.json()["monthly_interest_rate"]) == Decimal("0.02")
    assert Decimal(purchase.json()["installments"][0]["estimated_interest"]) == Decimal("20000")
    future_purchase = client.post(
        f"/api/cards/{card_id}/purchases",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "purchase-future-rate"},
        json={
            "card_id": card_id,
            "category_id": food["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2027-01-10",
            "installments_count": 5,
            "description": "Compra con nueva tasa",
        },
    )
    assert future_purchase.status_code == 201, future_purchase.text
    assert Decimal(future_purchase.json()["monthly_interest_rate"]) == Decimal("0.021234567891")
    assert client.post(
        f"/api/cards/{card_id}/purchases",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "purchase-1"},
        json={
            "card_id": card_id,
            "category_id": food["id"],
            "amount": "1000000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 5,
            "description": "Computador",
        },
    ).status_code == 200

    card_details = client.get(f"/api/cards/{card_id}").json()
    assert card_details["currencies"][0]["outstanding_debt"] == "1100000"
    assert Decimal(card_details["interest_rates"][0]["monthly_rate"]) == Decimal("0.021234567891")
    transactions = client.get("/api/transactions")
    assert transactions.status_code == 200, transactions.text
    card_transaction = next(item for item in transactions.json() if item["credit_purchase_id"] == purchase.json()["id"])
    assert card_transaction["account_id"] is None
    assert card_transaction["card_id"] == card_id
    assert card_transaction["payment_method"] == "credit"
    payment = client.post(
        f"/api/cards/{card_id}/payments",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "payment-1"},
        json={
            "card_id": card_id,
            "source_account_id": source["id"],
            "obligation_amount": "250000",
            "obligation_currency": "COP",
            "payment_date": "2026-02-01",
        },
    )
    assert payment.status_code == 201, payment.text
    assert client.get(f"/api/cards/{card_id}").json()["currencies"][0]["outstanding_debt"] == "850000"
    assert client.get(f"/api/accounts/{source['id']}").json()["current_balance"] == "1750000"


def test_usd_purchase_and_cop_payment_records_conversion(client):
    csrf = register(client)
    source = account(client, csrf)
    categories = client.get("/api/categories").json()
    food = next(item for item in categories if item["name"] == "Alimentación")
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Visa USD", "statement_closing_day": 31, "currencies": [{"currency": "USD"}]},
    ).json()
    purchase = client.post(
        f"/api/cards/{card['id']}/purchases",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "category_id": food["id"],
            "amount": "25",
            "currency": "USD",
            "purchase_date": "2026-01-20",
            "installments_count": 1,
            "description": "Suscripción",
        },
    )
    assert purchase.status_code == 201, purchase.text
    payment = client.post(
        f"/api/cards/{card['id']}/payments",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "source_account_id": source["id"],
            "obligation_amount": "25",
            "obligation_currency": "USD",
            "source_amount": "100000",
            "exchange_rate": "4000",
            "payment_date": "2026-02-01",
        },
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["source_currency"] == "COP"
    assert Decimal(client.get(f"/api/cards/{card['id']}").json()["currencies"][0]["outstanding_debt"]) == Decimal("0")
    assert client.get(f"/api/accounts/{source['id']}").json()["current_balance"] == "1900000"


def test_card_debt_adjustment_is_grouped_by_currency(client):
    csrf = register(client)
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Ajuste", "statement_closing_day": 15, "currencies": [{"currency": "COP"}, {"currency": "USD"}]},
    ).json()
    adjustment = client.post(
        f"/api/cards/{card['id']}/balance-adjustments",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "card-adjustment-1"},
        json={"currency": "COP", "target_debt": "250000", "adjustment_date": "2026-01-15", "description": "Conciliación"},
    )
    assert adjustment.status_code == 200, adjustment.text
    details = adjustment.json()
    cop = next(item for item in details["currencies"] if item["currency"] == "COP")
    usd = next(item for item in details["currencies"] if item["currency"] == "USD")
    assert cop["outstanding_debt"] == "250000"
    assert Decimal(usd["outstanding_debt"]) == Decimal("0")


def test_card_with_no_movements_has_zero_debt(client):
    csrf = register(client)
    response = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Sin deuda", "statement_closing_day": 15, "currencies": [{"currency": "COP"}]},
    )
    assert response.status_code == 201, response.text
    card = client.get("/api/cards").json()[0]
    assert card["currencies"][0]["outstanding_debt"] == "0"


def test_credit_purchase_transaction_can_be_deleted(client):
    csrf = register(client)
    categories = client.get("/api/categories").json()
    food = next(item for item in categories if item["name"] == "Alimentación")
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "COP"}]},
    ).json()
    purchase = client.post(
        f"/api/cards/{card['id']}/purchases",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "category_id": food["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 3,
            "description": "Compra a crédito",
        },
    )
    assert purchase.status_code == 201, purchase.text
    assert client.get(f"/api/cards/{card['id']}").json()["currencies"][0]["outstanding_debt"] == "100000"
    transaction = next(item for item in client.get("/api/transactions").json() if item["credit_purchase_id"] == purchase.json()["id"])
    deleted = client.delete(
        f"/api/transactions/{transaction['id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/cards/{card['id']}").json()["currencies"][0]["outstanding_debt"] == "0"
    remaining = [item for item in client.get("/api/transactions").json() if item["credit_purchase_id"] == purchase.json()["id"]]
    assert remaining == []


def test_credit_purchase_transaction_cannot_be_edited(client):
    csrf = register(client)
    food = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "COP"}]},
    ).json()
    purchase = client.post(
        f"/api/cards/{card['id']}/purchases",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "category_id": food["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 1,
            "description": "Compra a crédito",
        },
    )
    assert purchase.status_code == 201
    transaction = next(item for item in client.get("/api/transactions").json() if item["credit_purchase_id"] == purchase.json()["id"])
    response = client.patch(
        f"/api/transactions/{transaction['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"description": "Modificada"},
    )
    assert response.status_code == 422
