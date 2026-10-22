from decimal import Decimal, ROUND_HALF_UP


CURRENCIES = {"COP": 0, "USD": 2}


def normalize_currency(currency: str) -> str:
    value = currency.upper()
    if value not in CURRENCIES:
        raise ValueError("Moneda no soportada")
    return value


def normalize_amount(amount: Decimal, currency: str, *, positive: bool = True) -> Decimal:
    currency = normalize_currency(currency)
    amount = Decimal(str(amount))
    if positive and amount <= 0:
        raise ValueError("El monto debe ser mayor que cero")
    quantum = Decimal(1).scaleb(-CURRENCIES[currency])
    normalized = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    if positive and normalized <= 0:
        raise ValueError("El monto es demasiado pequeño para la moneda")
    return normalized
