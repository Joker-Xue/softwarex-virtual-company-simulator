# Virtual Company Simulator for Career Planner

This repository stage contains the virtual-company simulator and reproducibility assets prepared for a SoftwareX submission. The artifact focuses on an AI-driven office world in which MBTI-shaped agents work, socialize, join company events, and evolve through a shared simulation loop exposed through a FastAPI backend and a Vue 3 frontend.

The formal SoftwareX submission release for this public artifact is `v1.0.0`.

The public SoftwareX package should be curated from the simulator boundary documented in `docs/softwarex_submission_boundary.md`. This staging branch still lives inside the private monorepo so that the simulator can be stabilized, documented, and exported cleanly.

## Why This Artifact Exists

- Reproduce the virtual-company simulation described in the manuscript.
- Provide a reviewer-friendly runnable demo with diagnostics and NPC recovery endpoints.
- Ship the experiment scripts and baseline outputs needed to validate behavior consistency, ablation, tick latency, and service availability.

## Architecture

```mermaid
flowchart LR
    UI["Vue 3 Reviewer UI\nAgentWorldView + Pinia + WebSocket"] --> API["FastAPI Backend\napp/main.py"]
    API --> LOOP["Simulation Loop\napp/engine/simulation_loop.py"]
    API --> EVENTS["Dynamic Event Engine\napp/engine/event_engine.py"]
    API --> NPC["NPC Seeder + Rebuild\napp/engine/npc_seeder.py"]
    LOOP --> DB["PostgreSQL\nagent profiles / tasks / events / rooms"]
    API --> REDIS["Redis\ncache + auxiliary services"]
    LOOP --> WS["World WebSocket\n/ws/world"]
    EVENTS --> DB
    NPC --> DB
    EXP["experiments/*.py"] --> API
    EXP --> LOOP
    RES["results/*"] --> DOCS["docs/EXPERIMENTS.md\nassets/figures/*"]
```

## Repository Layout

```text
app/
  engine/                 simulation loop, event engine, NPC seeding, MBTI logic
  routers/                simulation, world, personality, websocket endpoints
frontend/
  src/views/AgentWorldView.vue
  src/stores/agentWorld.ts
  src/utils/websocket.ts
experiments/              reproducibility scripts used in the SoftwareX package
results/                  baseline outputs regenerated from the current code
docs/DEPLOYMENT.md        reviewer startup and troubleshooting guide
docs/EXPERIMENTS.md       experiment commands, baselines, and tolerance notes
assets/figures/           screenshot and runtime evidence files
tests/                    virtual-company regression coverage
```

## Requirements

- Windows 10/11 or a compatible environment capable of running the provided batch launchers
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+
- Redis 7+

## Quick Start

### 1. Create local configuration

Copy `.env.example` to `.env` and fill in at least:

- `SECRET_KEY`
- `ENCRYPTION_KEY_V1`
- `LLM_API_KEY`
- `TIANAPI_KEY`

Keep `CORS_ORIGINS` on canonical localhost origins such as `http://localhost:5173`.

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
npm install
```

### 3. Start the stack

Preferred reviewer path:

```bat
start.bat
```

This launcher verifies Python, Node.js, npm, bootstrap scripts, and the required simulation endpoints before reporting success.

Manual startup is also supported:

```bat
scripts\start_backend.cmd
scripts\start_frontend.cmd
```

Canonical local URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

## Reviewer Smoke Checks

After startup, verify:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/simulation/status
curl http://localhost:8000/api/simulation/diagnostics
curl -X POST http://localhost:8000/api/simulation/rebuild-npcs
```

The NPC recovery acceptance gate is:

- `distribution.by_floor` includes non-zero population on `2F`
- `gates.top1_hotspot_ratio_lt_0_40` is `true`

## Simulator API Summary

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/simulation/status` | `GET` | Returns tick counters, speed, and aggregate agent counts |
| `/api/simulation/speed` | `POST` | Adjusts simulation speed multiplier |
| `/api/simulation/seed-npcs` | `POST` | Idempotently seeds NPCs |
| `/api/simulation/rebuild-npcs` | `POST` | Rebuilds NPC records and semantic positions |
| `/api/simulation/diagnostics` | `GET` | Returns runtime fingerprint, floor distribution, hotspots, and acceptance gates |
| `/api/world/map` | `GET` | Returns room geometry and interior metadata |
| `/ws/world` | `WebSocket` | Streams world updates to the frontend |

## Experiments

Formal reproduction scripts live in `experiments/` and current baselines live in `results/`.

Run all four manuscript-facing experiments:

```bash
python experiments/run_behavior_consistency.py --ticks 1000 --seed 42 --output results/behavior_consistency.csv
python experiments/run_ablation.py --condition all --trials 1000 --seed 42 --output results/ablation.csv
python experiments/run_tick_benchmark.py --warmup 10 --ticks 50 --output results/tick_benchmark.json
python experiments/run_availability_probe.py --duration-seconds 60 --output results/availability.json
```

The full protocol, expected fields, and rerun tolerance notes are documented in `docs/EXPERIMENTS.md`.

## Runtime Evidence

Agent world running screenshot:

![Agent world running](assets/figures/agent-world-running.png)

Additional reviewer-facing evidence:

- `assets/figures/diagnostics-sample.json`
- `assets/figures/rebuild-npcs-acceptance.json`
- `results/behavior_consistency.csv`
- `results/ablation.csv`
- `results/tick_benchmark.json`
- `results/availability.json`

## Tests

The core virtual-company regression suites are:

```bash
pytest -q tests/test_virtual_company_demo.py tests/test_virtual_company_upgrade.py
```

If you change CORS, login, or captcha behavior, also run:

```bash
pytest -q tests/test_cors_origins.py
pytest -q tests/test_captcha.py
```

## License

This software is released under the MIT License. See `LICENSE`.

## Citation

Citation metadata is provided in `CITATION.cff`. Update the repository URL and manuscript author list if the final public SoftwareX repository uses a different name than this staging branch assumes.

