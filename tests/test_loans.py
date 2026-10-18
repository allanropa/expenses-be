from datetime import date
from decimal import Decimal

from app.domain.loans import amortization_schedule, monthly_rate_from_effective_annual


def test_effective_annual_rate_and_fixed_schedule_reconcile():
    monthly = monthly_rate_from_effective_annual(Decimal("0.1268250301"))
    assert abs(monthly - Decimal("0.01")) < Decimal("0.0000001")
    monthly, schedule = amortization_schedule(Decimal("1000000"), "COP", Decimal("0.1268250301"), 12, date(2026, 2, 15))
    assert len(schedule) == 12
    assert sum(item.principal for item in schedule) == Decimal("1000000")
    assert schedule[0].total == schedule[1].total
    assert schedule[-1].due_date == date(2027, 1, 15)


def register(client):
    return client.post(
        "/api/auth/register",
        json={"email": "loan@example.com", "password": "correct horse", "display_name": "Loan User"},
    ).json()["csrf_token"]


def test_received_loan_can_skip_income_and_accept_extra_principal_payment(client):
    csrf = register(client)
    account = client.post(
        "/api/accounts",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Cuenta", "account_type": "checking", "currency": "COP", "opening_balance": "2000000", "opening_balance_date": "2026-01-01"},
    ).json()
    loan = client.post(
        "/api/loans",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Préstamo personal",
            "principal_amount": "1000000",
            "currency": "COP",
            "annual_effective_rate": "0.1268250301",
            "term_months": 12,
            "start_date": "2026-01-01",
            "first_payment_date": "2026-02-01",
            "source_account_id": account["id"],
            "record_as_income": False,
        },
    )
    assert loan.status_code == 201, loan.text
    assert loan.json()["outstanding_principal"] == "1000000"
    assert client.get(f"/api/accounts/{account['id']}").json()["current_balance"] == "3000000"
    payment = client.post(
        f"/api/loans/{loan.json()['id']}/payments",
        headers={"X-CSRF-Token": csrf},
        json={"source_account_id": account["id"], "payment_date": "2026-02-01", "extra_principal": "100000"},
    )
    assert payment.status_code == 201, payment.text
    assert Decimal(payment.json()["extra_principal"]) == Decimal("100000")
    assert Decimal(client.get(f"/api/loans/{loan.json()['id']}").json()["outstanding_principal"]) < Decimal("1000000")
    transactions = client.get("/api/transactions").json()
    payment_txs = [t for t in transactions if t["transaction_type"] == "payment"]
    assert len(payment_txs) == 1
    assert Decimal(payment_txs[0]["amount"]) > 0
    assert "capital" in payment_txs[0]["description"]
