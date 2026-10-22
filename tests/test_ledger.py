

def register(client, email="ana@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse", "display_name": "Ana"},
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def account(client, csrf, name="Cuenta principal", currency="COP", opening_balance="100000"):
    response = client.post(
        "/api/accounts",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": name,
            "account_type": "checking",
            "currency": currency,
            "opening_balance": opening_balance,
            "opening_balance_date": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_defaults_accounts_transactions_and_reversible_delete(client):
    csrf = register(client)
    categories = client.get("/api/categories").json()
    assert {category["name"] for category in categories} >= {"Alimentación", "Salario"}
    expense_category = next(item for item in categories if item["name"] == "Alimentación")
    income_category = next(item for item in categories if item["name"] == "Salario")
    checking = account(client, csrf)

    expense = client.post(
        "/api/transactions",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "expense-1"},
        json={
            "transaction_type": "expense",
            "amount": "12500",
            "currency": "COP",
            "transaction_date": "2026-01-05",
            "account_id": checking["id"],
            "category_id": expense_category["id"],
            "description": "Almuerzo",
        },
    )
    assert expense.status_code == 201, expense.text
    assert client.post(
        "/api/transactions",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "expense-1"},
        json={
            "transaction_type": "expense",
            "amount": "12500",
            "currency": "COP",
            "transaction_date": "2026-01-05",
            "account_id": checking["id"],
            "category_id": expense_category["id"],
        },
    ).status_code == 200

    income = client.post(
        "/api/transactions",
        headers={"X-CSRF-Token": csrf},
        json={
            "transaction_type": "income",
            "amount": "50000",
            "currency": "COP",
            "transaction_date": "2026-01-06",
            "account_id": checking["id"],
            "category_id": income_category["id"],
        },
    )
    assert income.status_code == 201, income.text
    assert client.get("/api/accounts").json()[0]["current_balance"] == "137500"

    deleted = client.delete(
        f"/api/transactions/{expense.json()['id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204
    assert client.get("/api/accounts").json()[0]["current_balance"] == "150000"
    assert len(client.get("/api/transactions").json()) == 1
    assert len(client.get("/api/transactions?limit=1&offset=0").json()) == 1
    assert client.get("/api/transactions?limit=0").status_code == 422


def test_expense_cannot_exceed_account_balance(client):
    csrf = register(client)
    checking = account(client, csrf, opening_balance="100")
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")

    response = client.post(
        "/api/transactions",
        headers={"X-CSRF-Token": csrf},
        json={
            "transaction_type": "expense",
            "amount": "101",
            "currency": "COP",
            "transaction_date": "2026-01-05",
            "account_id": checking["id"],
            "category_id": category["id"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "El gasto supera el saldo disponible de la cuenta"
    assert client.get("/api/accounts").json()[0]["current_balance"] == "100"


def test_transfer_is_atomic_and_multicurrency_is_explicit(client):
    csrf = register(client)
    source = account(client, csrf, "COP", "COP", "1000000")
    destination = account(client, csrf, "USD", "USD", "0")
    invalid = client.post(
        "/api/transfers",
        headers={"X-CSRF-Token": csrf},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "source_amount": "100000",
            "transfer_date": "2026-01-10",
        },
    )
    assert invalid.status_code == 422

    transfer = client.post(
        "/api/transfers",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "transfer-1"},
        json={
            "source_account_id": source["id"],
            "destination_account_id": destination["id"],
            "source_amount": "100000",
            "destination_amount": "25",
            "exchange_rate": "4000",
            "transfer_date": "2026-01-10",
        },
    )
    assert transfer.status_code == 201, transfer.text
    assert client.get("/api/accounts").json()[0]["current_balance"] == "900000"
    assert client.get("/api/accounts").json()[1]["current_balance"] == "25.00"
    listed = client.get("/api/transactions").json()
    assert listed[0]["entry_type"] == "transfer"
    assert listed[0]["destination_account_id"] == destination["id"]
    recent = client.get("/api/dashboard").json()["recent_transactions"]
    assert recent[0]["entry_type"] == "transfer"
    assert recent[0]["destination"] == destination["name"]


def test_account_and_transaction_are_isolated_between_users(client):
    csrf = register(client, "first@example.com")
    first = account(client, csrf)
    client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    second_csrf = register(client, "second@example.com")
    assert client.get(f"/api/accounts/{first['id']}").status_code == 404
    assert client.patch(
        f"/api/accounts/{first['id']}",
        headers={"X-CSRF-Token": second_csrf},
        json={"name": "Robada"},
    ).status_code == 404


def test_account_balance_edit_is_an_auditable_adjustment(client):
    csrf = register(client)
    checking = account(client, csrf, opening_balance="100000")
    adjustment = client.post(
        f"/api/accounts/{checking['id']}/balance-adjustments",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "balance-adjustment-1"},
        json={"target_balance": "250000", "adjustment_date": "2026-01-15", "description": "Conciliación bancaria"},
    )
    assert adjustment.status_code == 200, adjustment.text
    assert adjustment.json()["current_balance"] == "250000"
    assert client.get("/api/transactions").json() == []
