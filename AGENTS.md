# AGENTS.md

## Working Directory Matters

All server commands must run from `server/` (that's where `pyproject.toml` and `alembic.ini` live):

```bash
cd server && pytest tests/ -v
cd server && ruff check app/ tests/ --select E,F,W,B,S --ignore E501,S101
cd server && alembic upgrade head
cd server && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend commands run from `server/frontend/`. Client tests run from `client/`.

## Lint Command (Exact)

The CI lint command is specific about rule selection:

```bash
ruff check app/ tests/ --select E,F,W,B,S --ignore E501,S101
```

No `ruff format`, `black`, `mypy`, or `pyright` is configured. Format and type checks are not enforced.

## Testing

### Server tests

- Use in-memory SQLite (`sqlite+aiosqlite:///:memory:`), no external DB or Docker needed.
- `conftest.py` sets env vars **before** importing app modules — if you import `app.*` before setting env vars, tests fail.
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed on async tests.
- DB interactions are mocked at the SQLAlchemy session level (`AsyncMock`/`MagicMock`), not via a real DB.
- `CA_KEY_ENCRYPTION_KEY` must be a valid Fernet key (base64-encoded 32 bytes). Use `Fernet.generate_key().decode()` to generate one.

### Frontend E2E tests

- Playwright with Chromium only. Mock API responses via `page.route()` — no backend needed.
- Auth set via `sessionStorage.setItem('admin_api_key', key)` in `page.addInitScript()`.
- `npm run test:e2e` from `server/frontend/`.

### Client tests

- `conftest.py` adds `client/agent/` to `sys.path`. Run from `client/` directory.
- CI installs deps explicitly: `pip install httpx cryptography pytest pytest-asyncio`.

## Database Dual-Mode

- **SQLite (local dev)**: Tables auto-create on startup via `main.py` lifespan. No Alembic needed.
- **PostgreSQL (production/Docker)**: Must run `alembic upgrade head` before starting the app.
- Docker entrypoint runs `alembic upgrade head && uvicorn ...` automatically.
- `start.sh` / `startup.ps1` auto-switch `DATABASE_URL` to SQLite for local dev and generate `.env` + CA certs.

## Fernet Encryption

Private keys are encrypted at rest with Fernet. The `CA_KEY_ENCRYPTION_KEY` env var must be a valid Fernet key. Generate one:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

The Settings model validator rejects empty strings at startup.

## Dual-Port Architecture (Dev vs Production)

- **Local dev**: Single port (8000). No nginx. Auth still enforced unless `DEV_MODE=true`.
- **Production/Docker**: nginx on ports 443 (Control/Dashboard) and 8443 (Agent API). Port 443 blocks `/api/agent/` with 403.
- `DEV_MODE=true` bypasses `X-Agent-Token` auth — any active agent can access Agent API endpoints without a token.

## Frontend Dev Proxy

`vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`. If backend runs on a different port, edit the proxy target there.

## Key Patterns

- **App factory**: `create_app()` in `main.py` returns FastAPI instance. `app = create_app()` at module level for uvicorn.
- **Settings singleton**: `get_settings()` uses `@lru_cache` — reads env once.
- **Audit logging**: All write operations go through `write_audit()` in `core/audit.py`. AuditLog is append-only.
- **SPA fallback**: Main app serves `frontend/dist/` and catches non-API routes to `index.html`.

## Frontend Type Check

```bash
cd server/frontend && npx tsc --noEmit
```

This runs in CI. ESLint: `npm run lint`.

## Agent Cross-Compilation

```bash
# Go
cd client/agent-go && GOOS=linux GOARCH=amd64 go build -o dist/cert-agent-linux-amd64 ./cmd/cert-agent

# Rust (LTO enabled in release profile)
cd client/agent-rust && cargo build --release --target x86_64-unknown-linux-gnu
```