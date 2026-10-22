from enum import StrEnum


class CategoryKind(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    BOTH = "both"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    PAYMENT = "payment"


class TransactionStatus(StrEnum):
    ACTIVE = "active"
    VOIDED = "voided"


class PaymentMethod(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class BudgetScope(StrEnum):
    GENERAL = "general"
    CATEGORY = "category"
    ACCOUNT = "account"
    CARD = "card"


class BudgetType(StrEnum):
    MAXIMUM = "maximum"
    DAILY = "daily"


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class SpendingType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class OperationStatus(StrEnum):
    ACTIVE = "active"
    VOIDED = "voided"


class LoanStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class InstallmentStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
