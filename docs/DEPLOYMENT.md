# Deployment Guide

This guide is written for SoftwareX reviewers and maintainers who need a reliable way to start the virtual-company simulator locally.

Permanent archive DOI: [10.5281/zenodo.20053670](https://doi.org/10.5281/zenodo.20053670). The `v1.2.0` DOI release is intended to be run through the Docker one-command path below.

## Preferred Local Topology

- Frontend host: `http://localhost:5174`
- Backend host: `http://localhost:8000`
- Database: PostgreSQL on `localhost:5432`
- Cache and auxiliary services: Redis on `localhost:6379`

Do not mix `localhost` and `127.0.0.1` in default configuration files unless a targeted test requires it. The project normalizes loopback aliases in backend code, but the canonical local documentation path is `localhost`.

## Prerequisites

- Docker Desktop with Docker Compose for the one-command reviewer path
- Python 3.11+
- Node.js 20+
- npm 10+
- PostgreSQL 15+
- Redis 7+

## One-Command Docker Startup

From the repository root:

```bash
docker compose up --build
```

This starts the complete interactive stack:

- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- FastAPI backend on `http://localhost:8000`
- Vue frontend on `http://localhost:5174`

The Docker path is the recommended reviewer path for reproducing the full interactive system.

The public Docker path runs in reviewer mode by default. During registration,
request a verification code and enter `000000`. For a real SMTP-backed flow,
set `REVIEWER_MODE=false` and provide local `SMTP_*` values in `.env` before
starting Docker. See `docs/REVIEWER_MODE.md` for the reviewer-mode note.

## Manual Configuration

1. Copy `.env.example` to `.env`.
2. Update at least:
   - `SECRET_KEY`
   - `ENCRYPTION_KEY_V1`
   - `LLM_API_KEY`
   - `TIANAPI_KEY`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASSWORD`
   - `SMTP_FROM`
3. For public reviewer deployment without SMTP, keep:

```env
REVIEWER_MODE=true
REVIEWER_VERIFICATION_CODE=000000
```

4. Keep `CORS_ORIGINS` aligned with the canonical frontend origin:

```env
CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
```

Optional simulator tuning:

```env
DYNAMIC_EVENT_INTERVAL_SECONDS=3600
```

## Database Initialization

The application calls `init_db()` during startup, so a first boot can create missing tables automatically. Alembic remains available if you prefer explicit migrations:

```bash
alembic upgrade head
```

The default asynchronous connection string is:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/career_planner
```

## Redis Startup

Start Redis locally before launching the application:

```bash
redis-server
```

If you use Docker for infrastructure only:

```bash
docker compose up -d redis
```

## Backend Startup

Preferred:

```bat
scripts\start_backend.cmd
```

Manual fallback:

```bash
python -m uvicorn app.main:app --host localhost --port 8000 --reload
```

Key reviewer endpoints:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/api/simulation/status`
- `http://localhost:8000/api/simulation/diagnostics`

## Frontend Startup

Preferred:

```bat
scripts\start_frontend.cmd
```

Manual fallback:

```bash
npm install
cd src/frontend
npm run dev -- --host localhost --port 5174
```

The frontend should target:

```env
VITE_API_BASE=http://localhost:8000
```

## One-Click Launcher

For reviewer convenience, use:

```bat
start.bat
```

What it does:

- verifies Python, Node.js, and npm
- installs backend dependencies if needed
- installs frontend dependencies if `node_modules` is missing
- checks ports `8000` and `5174`
- starts backend and frontend in separate windows
- waits for `/api/simulation/rebuild-npcs` and `/api/simulation/diagnostics` to appear in OpenAPI before reporting success

If the launcher fails the route gate, close old backend windows and rerun it.

## Docker Compose Details

`docker-compose.yml` is configured as a full-stack reviewer path:

```bash
docker compose up --build
```

It builds and starts `db`, `redis`, `api`, and `frontend`. Health checks gate service readiness so the frontend waits for the API, and the API waits for PostgreSQL and Redis.

## Reviewer Smoke Test

Run these after the stack is up:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/simulation/status
curl -X POST http://localhost:8000/api/simulation/rebuild-npcs
curl http://localhost:8000/api/simulation/diagnostics
curl -I http://localhost:5174
```

Acceptance criteria:

- `distribution.by_floor` includes `2F > 0`
- `gates.top1_hotspot_ratio_lt_0_40` is `true`

## Troubleshooting

### Frontend opens but APIs fail

- Confirm the browser origin is `http://localhost:5174`.
- Confirm backend CORS uses `localhost` origins and not only `127.0.0.1`.
- Re-run:

```bash
pytest -q tests/test_cors_origins.py
pytest -q tests/test_captcha.py
```

### NPCs cluster on one floor

Do not inspect the UI first. Run:

```bash
curl -X POST http://localhost:8000/api/simulation/rebuild-npcs
curl http://localhost:8000/api/simulation/diagnostics
```

Use the diagnostics response as the source of truth.

### Simulation endpoints are missing

- Make sure the backend process is serving the current branch and not an older instance.
- Re-run `start.bat` and wait for the route gate to pass.

### WebSocket indicator stays disconnected

- Verify `/ws/world` is reachable from the current frontend origin.
- Confirm the backend is running on `localhost:8000`.
- Reload the page after the backend is fully ready.

