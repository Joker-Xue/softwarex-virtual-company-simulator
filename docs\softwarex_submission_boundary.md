# SoftwareX Virtual Company Submission Boundary

## Purpose

This note defines the exact code and assets that should be included in the public GitHub repository for the SoftwareX submission. The public artifact should represent only the virtual-company simulator and its reproducibility package, not the full private monorepo.

## Public Repository Strategy

- Keep the current monorepo private as the development source of truth.
- Create a separate public repository for the SoftwareX submission artifact.
- Publish only the minimum complete, runnable, reviewable simulator package that matches the manuscript contribution.

## Mandatory Simulator Scope

### Backend core

- `app/main.py`
- `app/database.py`
- `app/engine/simulation_loop.py`
- `app/engine/agent_ai.py`
- `app/engine/npc_seeder.py`
- `app/engine/event_engine.py`
- `app/engine/schedule_engine.py`
- `app/engine/mbti_compat.py`
- `app/utils/runtime_fingerprint.py`
- `app/routers/agent_simulation.py`
- `app/routers/agent_personality.py`
- `app/routers/agent_ws.py`
- `app/routers/agent_world.py`
- simulator-related SQLAlchemy models under `app/models/`
- simulator-related schemas under `app/schemas/`
- prompt files only if LLM-assisted simulator decisions remain enabled in the published artifact

### Frontend minimum demo

- `frontend/src/views/AgentWorldView.vue`
- `frontend/src/stores/agentWorld.ts`
- `frontend/src/utils/websocket.ts`
- `frontend/src/constants/companyMap.ts`
- actually used simulator UI components under `frontend/src/components/agent/`
- required simulator styles, sprites, and related frontend utilities

### Runtime and startup assets

- `start.bat`
- `scripts/start_backend.cmd`
- `scripts/start_frontend.cmd`
- `requirements.txt`
- `frontend/package.json`
- `frontend/package-lock.json` if present
- `docker-compose.yml` if the container path is supported
- `.env.example`

### Validation and reproducibility

- `tests/test_virtual_company_demo.py`
- `tests/test_virtual_company_upgrade.py`
- all formal experiment scripts under `experiments/`
- all baseline outputs under `results/`

### Publication assets

- `README.md`
- `LICENSE`
- `CITATION.cff`
- `docs/DEPLOYMENT.md`
- `docs/EXPERIMENTS.md`
- `assets/figures/` screenshots and plot sources

## Optional Simulator Scope

Only keep these if the public demo actually depends on them:

- additional simulator-facing routers used by the world view
- prompt files for NPC or MBTI reasoning
- container deployment assets beyond the default local startup path
- sample diagnostics JSON or extra reviewer helper scripts

## Explicit Exclusions

Do not include these in the public SoftwareX repository unless the manuscript directly depends on them:

- resume parsing and resume workflow modules
- full job recommendation workflows unrelated to simulator validation
- report-generation modules unrelated to the simulator evidence package
- payment, shop, market, and unrelated business logic
- institution-specific deployment files
- private logs, uploaded files, local caches, and temporary exports
- unrelated demo features that expand review scope without supporting the paper

## Sensitive Material That Must Not Be Published

- `.env`
- machine-specific absolute paths
- private API keys or secrets
- database dumps with personal data
- `uploads/`
- local debug logs such as `backend.log`
- unreviewed temporary output directories

## Current Repository Alignment

The current monorepo already contains the core simulator paths needed for the public artifact, including:

- `app/engine/simulation_loop.py`
- `app/engine/event_engine.py`
- `app/engine/npc_seeder.py`
- `app/engine/schedule_engine.py`
- `app/engine/mbti_compat.py`
- `app/routers/agent_simulation.py`
- `app/routers/agent_personality.py`
- `app/routers/agent_ws.py`
- `app/routers/agent_world.py`
- `frontend/src/views/AgentWorldView.vue`
- `frontend/src/stores/agentWorld.ts`
- `frontend/src/utils/websocket.ts`
- `frontend/src/constants/companyMap.ts`
- `tests/test_virtual_company_demo.py`
- `tests/test_virtual_company_upgrade.py`

The public submission workflow should therefore focus on:

1. closing simulator gaps required by the SoftwareX guide,
2. adding the formal experiment package,
3. writing publication-grade docs and metadata,
4. copying only approved files into a new public repository.

## Boundary Decision Rule

If a file is not required to:

- run the simulator,
- render the simulator demo,
- validate the simulator behavior,
- reproduce the manuscript experiments, or
- help reviewers install, launch, and cite the software,

then it should stay out of the public submission repository.
