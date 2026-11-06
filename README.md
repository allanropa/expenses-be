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

## MCP

El endpoint MCP Streamable HTTP sin estado está disponible en `POST /mcp`.
Configura `MCP_API_TOKEN` con un secreto fijo y `MCP_USER_EMAIL` con el correo
del usuario activo cuyos datos se expondrán. El cliente debe enviar
`Authorization: Bearer <MCP_API_TOKEN>` en cada solicitud. Sin ambas variables
el acceso está deshabilitado. Usa un secreto largo y aleatorio, HTTPS fuera del
entorno local y cambia el token en la configuración para revocarlo. Este token
no sirve para la API REST. No se ofrece autenticación OAuth.

Las herramientas `list_categories`, `list_accounts` y `list_cards` devuelven
solo elementos activos del usuario autenticado. Las cuentas y tarjetas no
incluyen saldos, deuda, crédito disponible ni límites. El transporte devuelve
respuestas JSON y no admite conexiones SSE ni sesiones MCP persistentes.

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

## Lista permitida de registros

`REGISTRATION_EMAIL_WHITELIST` acepta correos separados por comas y compara sin
distinguir mayúsculas de minúsculas. Los registros están bloqueados si la
variable está vacía. Para desarrollo, `*` permite cualquier correo; en
producción se recomienda configurar únicamente las direcciones autorizadas.
