def test_spending_filters_only_change_chart_and_include_archived_sources(client):
    csrf = client.post("/api/auth/register", json={"email": "chart@example.com", "password": "correct horse", "display_name": "Ana"}).json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
    account = client.post("/api/accounts", headers=headers, json={"name": "Cuenta", "account_type": "checking", "currency": "COP", "opening_balance": "1000", "opening_balance_date": "2026-01-01"}).json()
    card = client.post("/api/cards", headers=headers, json={"name": "Tarjeta", "statement_closing_day": 15, "currencies": [{"currency": "COP"}]}).json()
    expense = client.post("/api/transactions", headers=headers, json={"transaction_type": "expense", "amount": "10", "currency": "COP", "transaction_date": "2026-01-05", "account_id": account["id"], "category_id": category["id"]})
    assert expense.status_code == 201, expense.text
    purchase = client.post(f"/api/cards/{card['id']}/purchases", headers=headers, json={"card_id": card["id"], "category_id": category["id"], "amount": "20", "currency": "COP", "purchase_date": "2026-01-05", "installments_count": 1, "description": "Compra"})
    assert purchase.status_code == 201, purchase.text
    assert client.post(f"/api/accounts/{account['id']}/archive", headers=headers).status_code == 200
    assert client.post(f"/api/cards/{card['id']}/archive", headers=headers).status_code == 200
    url = "/api/dashboard?date_from=2026-01-01&date_to=2026-01-31"
    all_data = client.get(url).json()
    debit = client.get(url + "&spending_method=debit").json()
    credit = client.get(url + "&spending_method=credit").json()
    by_account = client.get(url + f"&spending_account_id={account['id']}").json()
    by_card = client.get(url + f"&spending_card_id={card['id']}").json()
    assert float(all_data["spending_by_category"][0]["amount"]) == 30
    assert float(debit["spending_by_category"][0]["amount"]) == 10
    assert float(credit["spending_by_category"][0]["amount"]) == 20
    assert debit["spending_by_category"] == by_account["spending_by_category"]
    assert credit["spending_by_category"] == by_card["spending_by_category"]
    assert debit["consumption_by_currency"] == credit["consumption_by_currency"] == all_data["consumption_by_currency"]
    assert client.get(url + "&spending_card_id=99999").json()["spending_by_category"] == []
