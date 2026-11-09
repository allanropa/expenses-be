import json
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def mcp_config(monkeypatch):
    monkeypatch.setattr(settings, "mcp_api_token", "test-secret")
    monkeypatch.setattr(settings, "mcp_user_email", "one@example.com")
    monkeypatch.setattr("app.services.recurring.process_due_recurring_payments", lambda: None)


def rpc(client, method, params=None):
    return client.post("/mcp", headers={"Authorization": "Bearer test-secret"}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def register(client, email):
    response = client.post("/api/auth/register", json={"email": email, "password": "correct horse", "display_name": "Test"})
    assert response.status_code == 201
    return response.json()["csrf_token"]


def test_mcp_auth_and_protocol(client):
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    assert rpc(client, "tools/list").status_code == 401
    register(client, "one@example.com")
    initialized = rpc(client, "initialize", {"protocolVersion": "2025-03-26"}).json()
    assert initialized["result"]["protocolVersion"] == "2025-03-26"
    assert {tool["name"] for tool in rpc(client, "tools/list").json()["result"]["tools"]} == {"list_categories", "list_accounts", "list_cards", "list_transactions", "create_transaction"}
    assert rpc(client, "tools/call", {"name": "unknown"}).json()["error"]["code"] == -32602
    assert client.post("/mcp", headers={"Authorization": "Bearer test-secret"}, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202


def test_mcp_isolation_and_no_balances(client):
    csrf = register(client, "one@example.com")
    headers = {"X-CSRF-Token": csrf}
    assert client.post("/api/categories", headers=headers, json={"name": "Only one", "kind": "expense"}).status_code == 201
    assert client.post("/api/accounts", headers=headers, json={"name": "Private account", "account_type": "checking", "currency": "USD", "opening_balance": "1234", "opening_balance_date": "2025-01-01"}).status_code == 201
    assert client.post("/api/cards", headers=headers, json={"name": "Private card", "statement_closing_day": 15, "currencies": [{"currency": "USD"}]}).status_code == 201
    for tool in ("list_accounts", "list_cards"):
        text = rpc(client, "tools/call", {"name": tool}).json()["result"]["content"][0]["text"]
        assert len(json.loads(text)) == 1
        assert not any(word in text for word in ("balance", "debt", "credit_limit", "1234"))
    register(client, "two@example.com")
    settings.mcp_user_email = "two@example.com"
    for tool in ("list_categories", "list_accounts", "list_cards"):
        text = rpc(client, "tools/call", {"name": tool}).json()["result"]["content"][0]["text"]
        assert "Only one" not in text and "Private" not in text


def test_create_transaction_and_retry(client):
    csrf = register(client, "one@example.com")
    headers = {"X-CSRF-Token": csrf}
    account = client.post("/api/accounts", headers=headers, json={"name": "Cuenta", "account_type": "checking", "currency": "USD", "opening_balance": "100", "opening_balance_date": "2025-01-01"}).json()
    category = next(item for item in client.get("/api/categories").json() if item["kind"] == "expense")
    args = {"transaction_type": "expense", "amount": "10", "currency": "USD", "transaction_date": "2025-01-02", "account_id": account["id"], "category_id": category["id"], "idempotency_key": "request-1"}
    def call(payload):
        return rpc(client, "tools/call", {"name": "create_transaction", "arguments": payload}).json()["result"]

    first = call(args)
    assert not first.get("isError")
    assert json.loads(first["content"][0]["text"])["id"] == json.loads(call(args)["content"][0]["text"])["id"]
    assert call({**args, "amount": "20"})["isError"]
    assert call({**args, "idempotency_key": "request-2", "amount": "200"})["isError"]
    assert call({**args, "idempotency_key": "request-3", "account_id": 99999})["isError"]
    assert call({**args, "idempotency_key": ""})["isError"]
    assert len(client.get("/api/transactions").json()) == 1


def test_create_card_transaction_and_retry(client):
    csrf = register(client, "one@example.com")
    headers = {"X-CSRF-Token": csrf}
    card = client.post("/api/cards", headers=headers, json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "USD"}]}).json()
    category = next(item for item in client.get("/api/categories").json() if item["kind"] == "expense")
    args = {"transaction_type": "expense", "amount": "25", "currency": "USD", "transaction_date": "2025-01-02", "card_id": card["id"], "category_id": category["id"], "description": "Compra", "installments_count": 3, "idempotency_key": "card-1"}

    def call(payload):
        return rpc(client, "tools/call", {"name": "create_transaction", "arguments": payload}).json()["result"]

    first = call(args)
    assert not first.get("isError"), first
    transaction = json.loads(first["content"][0]["text"])
    assert transaction["card_id"] == card["id"] and transaction["payment_method"] == "credit"
    assert transaction["description"] == "Compra"
    assert json.loads(call(args)["content"][0]["text"])["id"] == transaction["id"]
    assert call({**args, "installments_count": 2})["isError"]
    assert call({**args, "idempotency_key": "card-2", "currency": "COP"})["isError"]
    assert call({**args, "idempotency_key": "card-3", "transaction_type": "income"})["isError"]
    purchases = client.get(f"/api/cards/{card['id']}/purchases").json()
    assert len(purchases) == 1 and len(purchases[0]["installments"]) == 3
    assert client.post(f"/api/cards/{card['id']}/archive", headers=headers).status_code == 200
    assert call({**args, "idempotency_key": "card-4"})["isError"]
    register(client, "two@example.com")
    settings.mcp_user_email = "two@example.com"
    assert call({**args, "idempotency_key": "card-5"})["isError"]


def test_list_transactions_filters_pagination_and_isolation(client):
    csrf = register(client, "one@example.com")
    headers = {"X-CSRF-Token": csrf}
    account = client.post("/api/accounts", headers=headers, json={"name": "Cuenta", "account_type": "checking", "currency": "USD", "opening_balance": "100", "opening_balance_date": "2025-01-01"}).json()
    other = client.post("/api/accounts", headers=headers, json={"name": "Otra", "account_type": "checking", "currency": "USD", "opening_balance": "0", "opening_balance_date": "2025-01-01"}).json()
    card = client.post("/api/cards", headers=headers, json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "USD"}]}).json()
    category = next(item for item in client.get("/api/categories").json() if item["kind"] == "expense")
    second_category = next(item for item in client.get("/api/categories").json() if item["kind"] == "expense" and item["id"] != category["id"])
    expense = client.post("/api/transactions", headers=headers, json={"transaction_type": "expense", "amount": "10", "currency": "USD", "transaction_date": "2025-01-02", "account_id": account["id"], "category_id": category["id"], "category_ids": [category["id"], second_category["id"]]})
    assert expense.status_code == 201
    purchase = client.post(f"/api/cards/{card['id']}/purchases", headers=headers, json={"card_id": card["id"], "category_id": category["id"], "amount": "5", "currency": "USD", "purchase_date": "2025-01-03", "installments_count": 1, "description": "Compra"})
    assert purchase.status_code == 201
    transfer = client.post("/api/transfers", headers=headers, json={"source_account_id": account["id"], "destination_account_id": other["id"], "source_amount": "2", "transfer_date": "2025-01-04"})
    assert transfer.status_code == 201

    def query(arguments):
        return rpc(client, "tools/call", {"name": "list_transactions", "arguments": arguments}).json()["result"]

    def items(arguments):
        return json.loads(query(arguments)["content"][0]["text"])

    assert len(items({})) == 3
    assert items({"transaction_type": "transfer"})[0]["entry_type"] == "transfer"
    assert len(items({"account_id": account["id"]})) == 2
    assert len(items({"card_id": card["id"], "category_id": category["id"]})) == 1
    assert len(items({"category_id": second_category["id"]})) == 1
    assert len(items({"date_from": "2025-01-03", "date_to": "2025-01-03"})) == 1
    first, second = items({"limit": 1, "offset": 0})[0], items({"limit": 1, "offset": 1})[0]
    assert (first["entry_type"], first["id"]) != (second["entry_type"], second["id"])
    assert items({"offset": 100}) == []
    assert query({"limit": 101})["isError"]
    assert query({"date_from": "2025-01-05", "date_to": "2025-01-01"})["isError"]
    assert query({"unknown": True})["isError"]
    register(client, "two@example.com")
    settings.mcp_user_email = "two@example.com"
    assert items({}) == []
