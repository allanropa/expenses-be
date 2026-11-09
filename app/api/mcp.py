"""Stateless MCP Streamable HTTP endpoint."""

import json
import secrets
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.ledger_schemas import TransactionCreate
from app.api.card_schemas import PurchaseCreate
from app.api.transactions import list_transactions_for_user, response_for
from app.api.pagination import Pagination
from app.core.config import settings
from app.db.session import get_db
from app.models.auth import User
from app.models.cards import CardCurrency, CreditCard, CreditPurchase
from app.models.ledger import Account, Category, FinancialOperation, FinancialTransaction
from app.services.ledger import create_transaction
from app.services.cards import create_purchase

router = APIRouter(tags=["mcp"])
PROTOCOLS = {"2025-03-26", "2025-06-18", "2025-11-25"}
class MCPTransactionCreate(TransactionCreate):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120, pattern=r"\S")


class MCPCardTransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_type: Literal["expense"]
    amount: Decimal = Field(gt=0, description="Monto positivo de la compra")
    currency: str
    transaction_date: date
    card_id: int
    category_id: int
    description: str = Field(min_length=1, max_length=2000)
    installments_count: int = Field(default=1, ge=1, le=120)
    idempotency_key: str = Field(min_length=1, max_length=120, pattern=r"\S")


class MCPTransactionList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date | None = None
    date_to: date | None = None
    transaction_type: Literal["income", "expense", "payment", "transfer"] | None = None
    account_id: int | None = Field(default=None, gt=0)
    card_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("La fecha inicial no puede ser posterior a la fecha final")
        return self


transaction_schema = {"type": "object", "anyOf": [MCPTransactionCreate.model_json_schema(), MCPCardTransactionCreate.model_json_schema()]}
TOOLS = [
    {"name": "list_categories", "description": "Lista las categorías activas del usuario.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "list_accounts", "description": "Lista las cuentas activas sin saldos.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "list_cards", "description": "Lista las tarjetas activas sin saldos ni deuda.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "list_transactions", "description": "Consulta movimientos activos, incluidos pagos y transferencias, con filtros y paginación; ordenados por creación descendente.", "inputSchema": MCPTransactionList.model_json_schema(), "annotations": {"readOnlyHint": True}},
    {"name": "create_transaction", "description": "Crea un ingreso o gasto en una cuenta, o un gasto con tarjeta. Para tarjeta indica card_id, description y opcionalmente installments_count. Usa una clave de idempotencia única por movimiento. No crea transferencias.", "inputSchema": transaction_schema, "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}},
]


def get_mcp_user(request: Request, db: Session = Depends(get_db)) -> User:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if not settings.mcp_api_token or not settings.mcp_user_email or scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), settings.mcp_api_token.encode()):
        raise HTTPException(status_code=401, detail="Token MCP inválido", headers={"WWW-Authenticate": "Bearer"})
    user = db.query(User).filter(User.email == settings.mcp_user_email.strip().lower(), User.is_active.is_(True)).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario MCP inválido")
    return user


def tool_data(name: str, user_id: int, db: Session) -> list[dict]:
    if name == "list_categories":
        rows = db.query(Category).filter(Category.user_id == user_id, Category.is_archived.is_(False)).order_by(Category.name).all()
        return [{"id": row.id, "name": row.name, "kind": row.kind} for row in rows]
    if name == "list_accounts":
        rows = db.query(Account).filter(Account.user_id == user_id, Account.is_archived.is_(False)).order_by(Account.name).all()
        return [{"id": row.id, "name": row.name, "account_type": row.account_type, "currency": row.currency, "description": row.description} for row in rows]
    rows = db.query(CreditCard).filter(CreditCard.user_id == user_id, CreditCard.is_archived.is_(False)).order_by(CreditCard.name).all()
    currencies = db.query(CardCurrency.card_id, CardCurrency.currency).filter(CardCurrency.card_id.in_([row.id for row in rows])).order_by(CardCurrency.currency).all()
    return [{"id": row.id, "name": row.name, "issuing_bank": row.issuing_bank, "statement_closing_day": row.statement_closing_day, "description": row.description, "currencies": [currency for card_id, currency in currencies if card_id == row.id]} for row in rows]


def create_mcp_transaction(arguments: dict, user_id: int, db: Session) -> dict:
    if "card_id" in arguments:
        return create_mcp_card_transaction(arguments, user_id, db)
    payload = MCPTransactionCreate.model_validate(arguments)
    key = "mcp:" + payload.idempotency_key
    operation = db.query(FinancialOperation).filter_by(user_id=user_id, idempotency_key=key).one_or_none()
    if operation:
        transaction = db.query(FinancialTransaction).filter_by(operation_id=operation.id, user_id=user_id).one_or_none()
        if transaction is None or any((
            transaction.transaction_type != payload.transaction_type,
            transaction.amount != payload.amount,
            transaction.currency != payload.currency,
            transaction.transaction_date != payload.transaction_date,
            transaction.account_id != payload.account_id,
            transaction.category_ids != list(dict.fromkeys(payload.category_ids or [payload.category_id])),
            transaction.description != payload.description,
            transaction.notes != payload.notes,
            transaction.is_recurring != payload.is_recurring,
        )):
            raise HTTPException(status_code=409, detail="La clave de idempotencia ya corresponde a otro movimiento")
        return response_for(transaction).model_dump(mode="json")
    account = db.query(Account).filter_by(id=payload.account_id, user_id=user_id, is_archived=False).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Cuenta activa no encontrada")
    try:
        transaction = create_transaction(db, user_id, payload, key)
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent request may have committed the same key first.
        if db.query(FinancialOperation).filter_by(user_id=user_id, idempotency_key=key).one_or_none():
            return create_mcp_transaction(arguments, user_id, db)
        raise
    return response_for(transaction).model_dump(mode="json")


def create_mcp_card_transaction(arguments: dict, user_id: int, db: Session) -> dict:
    payload = MCPCardTransactionCreate.model_validate(arguments)
    purchase_data = PurchaseCreate.model_validate({
        "card_id": payload.card_id, "category_id": payload.category_id,
        "amount": payload.amount, "currency": payload.currency,
        "purchase_date": payload.transaction_date, "installments_count": payload.installments_count,
        "description": payload.description,
    })
    key = "mcp:" + payload.idempotency_key
    operation = db.query(FinancialOperation).filter_by(user_id=user_id, idempotency_key=key).one_or_none()
    if operation:
        purchase = db.query(CreditPurchase).filter_by(operation_id=operation.id, user_id=user_id).one_or_none()
        if purchase is None or any((
            purchase.card_id != purchase_data.card_id,
            purchase.category_id != purchase_data.category_id,
            purchase.amount != purchase_data.amount,
            purchase.currency != purchase_data.currency,
            purchase.purchase_date != purchase_data.purchase_date,
            purchase.installments_count != purchase_data.installments_count,
            purchase.description != purchase_data.description.strip(),
        )):
            raise HTTPException(status_code=409, detail="La clave de idempotencia ya corresponde a otro movimiento")
        transaction = db.query(FinancialTransaction).filter_by(operation_id=operation.id, user_id=user_id).one()
        return response_for(transaction).model_dump(mode="json")
    card = db.query(CreditCard).filter_by(id=payload.card_id, user_id=user_id, is_archived=False).one_or_none()
    if card is None:
        raise HTTPException(status_code=404, detail="Tarjeta activa no encontrada")
    try:
        purchase = create_purchase(db, user_id, purchase_data, key)
        transaction = db.query(FinancialTransaction).filter_by(operation_id=purchase.operation_id, user_id=user_id).one()
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(FinancialOperation).filter_by(user_id=user_id, idempotency_key=key).one_or_none():
            return create_mcp_card_transaction(arguments, user_id, db)
        raise
    return response_for(transaction).model_dump(mode="json")


@router.post("/mcp")
async def mcp(request: Request, user: User = Depends(get_mcp_user), db: Session = Depends(get_db)):
    protocol = request.headers.get("MCP-Protocol-Version")
    if protocol and protocol not in PROTOCOLS:
        raise HTTPException(status_code=400, detail="Versión MCP no soportada")
    try:
        message = await request.json()
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}, status_code=400)
    method, request_id = message["method"], message.get("id")
    if "id" not in message:
        return Response(status_code=202)
    params = message.get("params", {})
    error = None
    result = None
    if not isinstance(params, dict):
        error = (-32602, "Invalid params")
    elif method == "initialize":
        requested = params.get("protocolVersion")
        result = {"protocolVersion": requested if isinstance(requested, str) and requested in PROTOCOLS else "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "expenses", "version": "0.1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in {tool["name"] for tool in TOOLS} or not isinstance(arguments, dict) or (name not in {"create_transaction", "list_transactions"} and arguments != {}):
            error = (-32602, "Unknown tool or invalid arguments")
        else:
            try:
                if name == "create_transaction":
                    data = create_mcp_transaction(arguments, user.id, db)
                elif name == "list_transactions":
                    params = MCPTransactionList.model_validate(arguments)
                    rows = list_transactions_for_user(
                        user_id=user.id, db=db, pagination=Pagination(limit=params.limit, offset=params.offset),
                        date_from=params.date_from, date_to=params.date_to, transaction_type=params.transaction_type,
                        account_id=params.account_id, card_id=params.card_id, category_id=params.category_id,
                    )
                    data = [row.model_dump(mode="json") for row in rows]
                else:
                    data = tool_data(name, user.id, db)
                result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
            except ValidationError as exc:
                result = {"isError": True, "content": [{"type": "text", "text": exc.json(include_url=False, include_context=False)}]}
            except HTTPException as exc:
                db.rollback()
                result = {"isError": True, "content": [{"type": "text", "text": str(exc.detail)}]}
    else:
        error = (-32601, "Method not found")
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error:
        payload["error"] = {"code": error[0], "message": error[1]}
    else:
        payload["result"] = result
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.api_route("/mcp", methods=["GET", "DELETE"])
def unsupported_transport(user: User = Depends(get_mcp_user)):
    return Response(status_code=405, headers={"Allow": "POST"})
