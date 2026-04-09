# Deployment Guide

This guide is written for SoftwareX reviewers and maintainers who need a reliable way to start the virtual-company simulator locally.

## Preferred Local Topology

- Frontend host: `http://localhost:5173`
- Backend host: `http://localhost:8000`
- Database: PostgreSQL on `localhost:5432`
- Cache and auxiliary services: Redis on `localhost:6379`

Do not mix `localhost` and `127.0.0.1` in default configuration files unless a targeted test requires it. The project normalizes loopback aliases in backend code, but the canonical local documentation path is `localhost`.

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm 10+
- PostgreSQL 15+
- Redis 7+

## Configuration

1. Copy `.env.example` to `.env`.
2. Update at least:
   - `SECRET_KEY`
   - `ENCRYPTION_KEY_V1`
   - `LLM_API_KEY`
   - `TIANAPI_KEY`
3. Keep `CORS_ORIGINS` aligned with the canonical frontend origin:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
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
npm run dev -- --host localhost --port 5173
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
- checks ports `8000` and `5173`
- starts backend and frontend in separate windows
- waits for `/api/simulation/rebuild-npcs` and `/api/simulation/diagnostics` to appear in OpenAPI before reporting success

If the launcher fails the route gate, close old backend windows and rerun it.

## Docker Compose Option

`docker-compose.yml` can be used when you want containerized infrastructure or a containerized backend:

```bash
docker compose up -d db redis api
```

The current reviewer recommendation is still local frontend plus either:

- local PostgreSQL and Redis, or
- `docker compose up -d db redis`

The `nginx` service is optional for manuscript review and is not required to reproduce the simulator experiments.

## Reviewer Smoke Test

Run these after the stack is up:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/simulation/status
curl -X POST http://localhost:8000/api/simulation/rebuild-npcs
curl http://localhost:8000/api/simulation/diagnostics
```

Acceptance criteria:

- `distribution.by_floor` includes `2F > 0`
- `gates.top1_hotspot_ratio_lt_0_40` is `true`

## Troubleshooting

### Frontend opens but APIs fail

- Confirm the browser origin is `http://localhost:5173`.
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

