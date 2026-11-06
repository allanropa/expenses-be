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
    assert {tool["name"] for tool in rpc(client, "tools/list").json()["result"]["tools"]} == {"list_categories", "list_accounts", "list_cards", "create_transaction"}
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
