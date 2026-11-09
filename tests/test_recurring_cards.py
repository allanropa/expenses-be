from datetime import date

from app.db.session import get_db
from app.main import app
from app.models.recurring import RecurringPayment
from app.services.recurring import process_payment


def test_recurring_card_purchase_and_edit_existing_marker(client):
    csrf = client.post("/api/auth/register", json={"email": "card@example.com", "password": "correct horse", "display_name": "Ana"}).json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    card = client.post("/api/cards", headers=headers, json={"name": "Visa", "statement_closing_day": 15, "currencies": [{"currency": "COP", "credit_limit": "10"}, {"currency": "USD", "credit_limit": "100"}]}).json()
    category = next(item for item in client.get("/api/categories").json() if item["name"] == "Alimentación")
    body = {"transaction_type": "expense", "card_id": card["id"], "currency": "USD", "amount": "20", "category_id": category["id"], "frequency": "monthly", "day_of_month": 1, "start_date": "2026-01-01", "description": "Suscripción"}
    response = client.post("/api/recurring-payments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["currency"] == "USD"
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        payment = db.get(RecurringPayment, response.json()["id"])
        process_payment(db, payment, date(2026, 1, 1))
        process_payment(db, payment, date(2026, 1, 1))
    finally:
        generator.close()
    transactions = client.get("/api/transactions").json()
    assert len(transactions) == 1
    assert transactions[0]["is_recurring"] is True
    assert transactions[0]["currency"] == "USD"
    purchases = client.get(f"/api/cards/{card['id']}/purchases").json()
    assert purchases[0]["installments_count"] == 1
    updated = client.patch(f"/api/transactions/{transactions[0]['id']}", headers=headers, json={"is_recurring": False})
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_recurring"] is False
    assert len(client.get("/api/recurring-payments").json()) == 1

    body.update(currency="COP", amount="20")
    insufficient = client.post("/api/recurring-payments", headers=headers, json=body).json()
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        payment = db.get(RecurringPayment, insufficient["id"])
        process_payment(db, payment, date(2026, 1, 1))
        assert payment.is_active and payment.last_processed_date == date(2026, 1, 1)
    finally:
        generator.close()
    assert len(client.get("/api/transactions").json()) == 1
    archived = client.post(f"/api/cards/{card['id']}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        payment = db.get(RecurringPayment, response.json()["id"])
        process_payment(db, payment, date(2026, 2, 1))
        assert payment.is_active and payment.last_processed_date == date(2026, 2, 1)
    finally:
        generator.close()
    assert len(client.get("/api/transactions").json()) == 1
