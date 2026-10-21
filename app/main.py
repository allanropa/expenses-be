from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import os

from app.api import accounts, auth, budgets, cards, categories, dashboard, loans, settings, transactions, transfers
from app.api.schemas import HealthResponse
from app.core.config import settings as app_settings
from app.db.session import engine

app = FastAPI(title="Personal Expense Tracker API", version="0.1.0")

# Configure CORS to allow frontend and localhost
cors_origins = [
    app_settings.frontend_origin,
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "https://expenses.lan.rpamplona.com",
    "http://expenses.lan.rpamplona.com",
    "https://expenses.rpamplona.com",
    "http://expenses.rpamplona.com",
]

# Add Docker network origins if in Docker environment
if os.getenv("DOCKER_ENV"):
    cors_origins.extend([
        "http://172.17.0.0:5173",
        "http://172.18.0.0:5173",
        "http://172.19.0.0:5173",
        "http://172.20.0.0:5173",
        "http://expenses-frontend:5173",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(transfers.router)
app.include_router(cards.router)
app.include_router(budgets.router)
app.include_router(dashboard.router)
app.include_router(loans.router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")
