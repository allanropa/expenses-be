# Backend (FastAPI)

API REST de finanzas personales.

## Requisitos

- Python 3.12+
- PostgreSQL (opcional; SQLite funciona para desarrollo local)

## Desarrollo local (sin Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

Con `DATABASE_URL=sqlite:///./expenses.db` no se necesita PostgreSQL.

## Pruebas

```bash
pytest
```

## Docker

Docker Compose requires `POSTGRES_PASSWORD` in `.env`; use a long random value.
The database is intentionally not published on the host network.

La imagen se construye desde `Dockerfile`. En el despliegue completo
(orquestado desde la raíz del repositorio) el servicio arranca con:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Las variables de entorno (`DATABASE_URL`, `COOKIE_SECURE`,
`FRONTEND_ORIGIN`, etc.) las inyecta `docker-compose.yml` en la raíz.
