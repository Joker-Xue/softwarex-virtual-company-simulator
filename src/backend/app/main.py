import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app import models as _models  # noqa: F401
from app.database import init_db
from app.routers import (
    agent_achievement,
    agent_analytics,
    agent_chat,
    agent_event,
    agent_friend,
    agent_group_chat,
    agent_meeting,
    agent_personality,
    agent_simulation,
    agent_social,
    agent_task,
    agent_world,
    agent_ws,
    auth,
)
from app.utils.cors import parse_cors_origins_from_env
from app.utils.runtime_fingerprint import get_runtime_fingerprint

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


DYNAMIC_EVENT_INTERVAL_SECONDS = _env_int("DYNAMIC_EVENT_INTERVAL_SECONDS", 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()

    from app.engine.achievement_engine import seed_achievements
    from app.engine.event_engine import check_dynamic_events
    from app.engine.npc_seeder import seed_npcs_standalone
    from app.engine.simulation_loop import start_simulation_loop

    await seed_achievements()
    try:
        await seed_npcs_standalone()
    except Exception as exc:
        logger.warning("NPC seeding on startup failed: %s", exc)

    async def _dynamic_event_loop():
        while True:
            try:
                await check_dynamic_events()
            except Exception as exc:
                logger.error("Dynamic event loop failed: %s", exc)
            await asyncio.sleep(DYNAMIC_EVENT_INTERVAL_SECONDS)

    sim_task = start_simulation_loop()
    event_task = asyncio.create_task(_dynamic_event_loop())

    try:
        fp = get_runtime_fingerprint()
        logger.info("Runtime fingerprint: %s", fp.get("fingerprint"))
    except Exception as exc:
        logger.warning("Runtime fingerprint build failed: %s", exc)

    try:
        yield
    finally:
        for task in [sim_task, event_task]:
            task.cancel()
        with suppress(Exception):
            await asyncio.gather(sim_task, event_task, return_exceptions=True)
        from app.database import engine as db_engine
        with suppress(Exception):
            await db_engine.dispose()


app = FastAPI(
    title="Virtual Company Simulator API",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

allowed_origins = parse_cors_origins_from_env(
    os.getenv("CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(agent_social.router, prefix="/api/agent", tags=["agent"])
app.include_router(agent_world.router, prefix="/api/world", tags=["world"])
app.include_router(agent_task.router, prefix="/api/task", tags=["task"])
app.include_router(agent_friend.router, prefix="/api/friend", tags=["friend"])
app.include_router(agent_chat.router, prefix="/api/agent-chat", tags=["chat"])
app.include_router(agent_group_chat.router, prefix="/api/agent-chat", tags=["group-chat"])
app.include_router(agent_event.router, prefix="/api/event", tags=["event"])
app.include_router(agent_ws.router, prefix="/ws", tags=["ws"])
app.include_router(agent_analytics.router, prefix="/api/agent", tags=["analytics"])
app.include_router(agent_meeting.router, prefix="/api/meeting", tags=["meeting"])
app.include_router(agent_achievement.router, prefix="/api/achievement", tags=["achievement"])
app.include_router(agent_simulation.router, prefix="/api/simulation", tags=["simulation"])
app.include_router(agent_personality.router, prefix="/api/agent", tags=["personality"])


@app.get("/", summary="API root")
async def root():
    return {"message": "Virtual Company Simulator API running", "docs": "/docs", "version": "1.0.0"}


@app.get("/health", summary="Health check")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}
