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
    assert {tool["name"] for tool in rpc(client, "tools/list").json()["result"]["tools"]} == {"list_categories", "list_accounts", "list_cards"}
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
