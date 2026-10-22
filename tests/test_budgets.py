from decimal import Decimal


def register(client):
    return client.post(
        "/api/auth/register",
        json={"email": "budget@example.com", "password": "correct horse", "display_name": "Budget User"},
    ).json()["csrf_token"]


def create_account(client, csrf, name="Cuenta"):
    return client.post(
        "/api/accounts",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": name,
            "account_type": "checking",
            "currency": "COP",
            "opening_balance": "1000000",
            "opening_balance_date": "2026-01-01",
        },
    ).json()


def test_maximum_and_daily_budgets_share_consumption_without_duplication(client):
    csrf = register(client)
    account = create_account(client, csrf)
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
    expense = client.post(
        "/api/transactions",
        headers={"X-CSRF-Token": csrf},
        json={
            "transaction_type": "expense",
            "amount": "50000",
            "currency": "COP",
            "transaction_date": "2026-01-01",
            "account_id": account["id"],
            "category_id": category["id"],
            "description": "Mercado",
        },
    )
    assert expense.status_code == 201
    maximum = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Máximo mensual",
            "budget_type": "maximum",
            "target_amount": "100000",
            "currency": "COP",
            "period_type": "monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "spending_type": "debit",
        },
    )
    daily = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Diario",
            "budget_type": "daily",
            "target_amount": "40000",
            "currency": "COP",
            "period_type": "custom",
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
            "spending_type": "debit",
        },
    )
    assert maximum.status_code == 201, maximum.text
    assert daily.status_code == 201, daily.text
    maximum_summary = client.get(f"/api/budgets/{maximum.json()['id']}/summary?date_from=2026-01-01&date_to=2026-01-31").json()
    daily_summary = client.get(f"/api/budgets/{daily.json()['id']}/summary?date_from=2026-01-01&date_to=2026-01-03").json()
    assert Decimal(maximum_summary["actual_spending"]) == Decimal("50000")
    assert Decimal(maximum_summary["balance"]) == Decimal("50000")
    assert Decimal(daily_summary["accumulated_budget"]) == Decimal("120000")
    assert Decimal(daily_summary["actual_spending"]) == Decimal("50000")
    assert Decimal(daily_summary["balance"]) == Decimal("70000")
    assert Decimal(daily_summary["equivalent_budget_days"]) == Decimal("1.75")


def test_credit_budget_counts_purchase_not_card_payment(client):
    csrf = register(client)
    account = create_account(client, csrf)
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
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
            "category_id": category["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 1,
            "description": "Compra crédito",
        },
    )
    assert purchase.status_code == 201, purchase.text
    budget = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Crédito",
            "budget_type": "maximum",
            "target_amount": "150000",
            "currency": "COP",
            "period_type": "monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "spending_type": "credit",
        },
    ).json()
    payment = client.post(
        f"/api/cards/{card['id']}/payments",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "source_account_id": account["id"],
            "obligation_amount": "100000",
            "obligation_currency": "COP",
            "payment_date": "2026-01-20",
        },
    )
    assert payment.status_code == 201, payment.text
    summary = client.get(f"/api/budgets/{budget['id']}/summary?date_from=2026-01-01&date_to=2026-01-31").json()
    assert Decimal(summary["actual_spending"]) == Decimal("100000")


def test_card_scoped_budget_counts_card_purchase(client):
    csrf = register(client)
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
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
            "category_id": category["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 1,
            "description": "Compra crédito",
        },
    )
    assert purchase.status_code == 201, purchase.text
    budget = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Tarjeta",
            "budget_type": "maximum",
            "target_amount": "150000",
            "currency": "COP",
            "period_type": "monthly",
            "scope": "card",
            "card_id": card["id"],
            "spending_type": "credit",
        },
    )
    assert budget.status_code == 201, budget.text
    summary = client.get(f"/api/budgets/{budget.json()['id']}/summary?date_from=2026-01-01&date_to=2026-01-31").json()
    assert Decimal(summary["actual_spending"]) == Decimal("100000")


def test_budget_detail_can_update_limit_and_recalculate(client):
    csrf = register(client)
    budget = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Editable",
            "budget_type": "maximum",
            "target_amount": "100000",
            "currency": "COP",
            "period_type": "monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "spending_type": "debit",
        },
    ).json()
    updated = client.patch(
        f"/api/budgets/{budget['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"target_amount": "200000", "name": "Editable 2"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["target_amount"] == "200000.0000"
    detail = client.get(f"/api/budgets/{budget['id']}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Editable 2"


def test_budget_scope_change_to_card_requires_a_card(client):
    csrf = register(client)
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
    card = client.post(
        "/api/cards",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "COP"}]},
    ).json()
    assert client.post(
        f"/api/cards/{card['id']}/purchases",
        headers={"X-CSRF-Token": csrf},
        json={
            "card_id": card["id"],
            "category_id": category["id"],
            "amount": "100000",
            "currency": "COP",
            "purchase_date": "2026-01-10",
            "installments_count": 1,
            "description": "Compra crédito",
        },
    ).status_code == 201
    budget = client.post(
        "/api/budgets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "General",
            "budget_type": "maximum",
            "target_amount": "150000",
            "currency": "COP",
            "period_type": "monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "spending_type": "credit",
        },
    ).json()
    rejected = client.patch(
        f"/api/budgets/{budget['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"scope": "card", "spending_type": "credit"},
    )
    assert rejected.status_code == 422
    accepted = client.patch(
        f"/api/budgets/{budget['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"scope": "card", "card_id": card["id"], "spending_type": "credit"},
    )
    assert accepted.status_code == 200, accepted.text
    summary = client.get(f"/api/budgets/{budget['id']}/summary?date_from=2026-01-01&date_to=2026-01-31").json()
    assert Decimal(summary["actual_spending"]) == Decimal("100000")


def test_alerts_collection_route_is_not_captured_as_budget_id(client):
    register(client)
    response = client.get("/api/budgets/alerts")
    assert response.status_code == 200
    assert response.json() == []
