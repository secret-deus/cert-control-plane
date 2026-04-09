# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cert Control Plane is a TLS certificate lifecycle management system. **Client-Server architecture**:
- **Server** (`server/`): FastAPI control plane + React dashboard + nginx reverse proxy
- **Client** (`client/`): Agent packages (Python/Go/Rust) running on nginx nodes

Key pattern: Admin uploads external certificates (e.g. from cloud providers) to the control plane, assigns them to agents, and agents pull updates via polling.

## Repository Layout

```
server/              # Control plane (backend + frontend + infra)
  app/               # FastAPI application
  alembic/           # Database migrations
  frontend/          # React dashboard
  nginx/             # Reverse proxy config (dual-port isolation)
  tests/             # Server-side tests
  pyproject.toml
  Dockerfile

client/              # Agent packages (deployed to nginx nodes)
  agent/             # Python agent (reference implementation)
  agent-go/          # Go agent
  agent-rust/        # Rust agent
  tests/             # Agent-side tests (deploy, installer)
  (each agent has its own pyproject.toml / Cargo.toml / go.mod)

/                    # Shared project files
  docker-compose.yml
  .env.example
  docs/
  scripts/
  tools/
  start.sh / startup.ps1   # One-click dev startup
```

## Common Commands

### Server (Backend)
```bash
cd server
pip install -e ".[dev]"           # Install with dev dependencies
pytest tests/ -v                  # Run server tests (uses SQLite, no DB needed)
pytest tests/test_rollout.py -v   # Run single test file
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  # Dev server
alembic upgrade head              # Run migrations
ruff check app/ tests/            # Lint (E,F,W,B,S rules)
```

### Client (Python Agent)
```bash
cd client
pytest tests/ -v                  # Run agent-side tests
pip install -e agent/             # Install agent package
python -m agent                   # Run agent
```

### Frontend (React)
```bash
cd server/frontend
npm install
npm run dev                       # Dev server at localhost:5173
npm run build                     # Production build
npm run lint                      # ESLint
```

### Docker
```bash
docker-compose up -d              # Start PostgreSQL + app + nginx
docker-compose up -d db           # Start only PostgreSQL
```

## Architecture

### Dual-Port Isolation
- **Port 443**: Control API + Dashboard, authenticated via `X-Admin-API-Key` header
- **Port 8443**: Agent API, TLS + `X-Agent-Token` authentication

Nginx reverse proxy enforces: 443 port cannot access Agent API endpoints (returns 403).

### Key Components

| Path | Purpose |
|------|---------|
| `server/app/api/agent.py` | Agent API: register (TOFU), fetch-certs, heartbeat |
| `server/app/api/control.py` | Control API: agent/cert/rollout management |
| `server/app/api/dashboard.py` | Dashboard API: summary, health, expiry events |
| `server/app/orchestrator/rollout.py` | Batch rollout orchestration with pause/resume/rollback |
| `server/app/registry/store.py` | Certificate CRUD operations |
| `server/app/core/crypto.py` | Fernet encryption for private keys |
| `server/app/core/security.py` | API key validation, token generation |
| `client/agent/` | Python agent (reference implementation) |

### Data Models (`server/app/models.py`)
- `Agent` - Registered nginx nodes with cert metadata
- `ExternalCertificate` - Uploaded external certificates
- `AgentCertAssignment` - Maps agent local_path to external cert
- `Certificate` - Certificate audit/deployment records
- `Rollout` / `RolloutItem` - Batch certificate rotation jobs
- `AuditLog` - Immutable audit trail

### Agent Registration Flow (TOFU)
1. Agent generates RSA keypair, computes fingerprint (SHA256 of DER public key)
2. Agent submits `{name, fingerprint}` to `/api/agent/register`
3. If new → creates agent with `pending_approval` status
4. If pre-created slot (fingerprint=None) → binds first observed fingerprint
5. Admin approves via Control API → agent polls `/register/status` for `agent_token`
6. Agent uses `X-Agent-Token` for all subsequent authenticated calls

### External Certificate Distribution
- Admin uploads external certificates (e.g. from cloud providers) via Control API
- Admin assigns external certs to agents via `AgentCertAssignment` (agent + local_path)
- Agent polls `/api/agent/fetch-certs` with current cert state, receives updates
- Private keys stored encrypted (Fernet) on control plane, decrypted on delivery

### Rollout Orchestration
- Batch-based certificate rotation across multiple agents
- Only agents with `IN_PROGRESS` rollout items may pull certificate updates
- Agents with `PENDING` items are gated until their batch is reached
- Rollout items are auto-completed when agent confirms deployment via fetch-certs
- Orchestrator ticks every 30s (configurable) to advance batches
- Supports: start, pause, resume, rollback operations

## Important Files

- `.env.example` - Required environment variables template
- `client/agent/agent.env.example` - Agent configuration template
- `server/nginx/nginx.conf` - Dual-port reverse proxy config
- `server/alembic/versions/` - Database migration files

## Security Considerations

- Private keys encrypted at rest (Fernet) in the control plane database
- Agent authentication uses `X-Agent-Token` issued after admin approval
- Revoked agents are immediately denied
- Rollout gating prevents unauthorized certificate pulls during batch operations
- All write operations are logged to immutable `audit_logs` table
