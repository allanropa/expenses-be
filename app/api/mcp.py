"""Stateless, read-only MCP Streamable HTTP endpoint."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.auth import User
from app.models.cards import CardCurrency, CreditCard
from app.models.ledger import Account, Category

router = APIRouter(tags=["mcp"])
PROTOCOLS = {"2025-03-26", "2025-06-18", "2025-11-25"}
TOOLS = [
    {"name": "list_categories", "description": "Lista las categorías activas del usuario.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "list_accounts", "description": "Lista las cuentas activas sin saldos.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "list_cards", "description": "Lista las tarjetas activas sin saldos ni deuda.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
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
        if not isinstance(name, str) or name not in {tool["name"] for tool in TOOLS} or params.get("arguments", {}) != {}:
            error = (-32602, "Unknown tool or invalid arguments")
        else:
            data = tool_data(name, user.id, db)
            result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
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
