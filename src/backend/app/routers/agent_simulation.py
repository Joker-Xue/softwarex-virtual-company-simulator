"""
simulation control endpoints
"""
import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_profile import AgentProfile
from app.engine.npc_seeder import (
    seed_npcs,
    reset_npc_positions,
    rebuild_npcs,
    get_simulation_distribution,
)
from app.engine.simulation_loop import get_status, set_speed
from app.utils.runtime_fingerprint import get_runtime_fingerprint

router = APIRouter()


@router.post("/seed-npcs", summary="Seed NPCs (idempotent)")
async def api_seed_npcs(db: AsyncSession = Depends(get_db)):
    count = await seed_npcs(db)
    return {"seeded": count}


@router.post("/reset-positions", summary="Immediately reset all AI characters to their correct floor locations")
async def api_reset_positions(db: AsyncSession = Depends(get_db)):
    """Clear the room Cache and reset the pos_x/pos_y of all AI characters by Department/Floor。"""
    count = await reset_npc_positions(db)
    return {"updated": count, "message": f"{count} AIRoles have been reset to the correct floor"}


@router.get("/status", summary="Simulation Status")
async def api_status(db: AsyncSession = Depends(get_db)):
    sim = get_status()
    result = await db.execute(
        select(func.count(AgentProfile.id)).where(AgentProfile.ai_enabled == True)
    )
    agent_count = result.scalar() or 0
    # Count total agents
    result2 = await db.execute(select(func.count(AgentProfile.id)))
    total = result2.scalar() or 0
    # Average career level
    result3 = await db.execute(select(func.avg(AgentProfile.career_level)))
    avg_level = round(result3.scalar() or 0, 1)
    return {
        **sim,
        "ai_agent_count": agent_count,
        "total_agents": total,
        "avg_career_level": avg_level,
    }


@router.post("/speed", summary="Adjust Simulation Speed")
async def api_speed(multiplier: float = Query(..., ge=0.5, le=10)):
    set_speed(multiplier)
    return get_status()


@router.post("/rebuild-npcs", summary="Rebuild NPC data and semantic positions")
async def api_rebuild_npcs(db: AsyncSession = Depends(get_db)):
    report = await rebuild_npcs(db)
    return {
        "ok": True,
        "report": report,
    }


@router.get("/diagnostics", summary="Runtime diagnostics (version fingerprint, floor distribution, hotspots)")
async def api_diagnostics(db: AsyncSession = Depends(get_db)):
    dist = await get_simulation_distribution(db)
    fp = get_runtime_fingerprint()
    top1_ratio = dist["hotspots"][0]["ratio"] if dist["hotspots"] else 0.0
    return {
        "ok": True,
        "runtime": {
            **fp,
            "pid": os.getpid(),
        },
        "distribution": dist,
        "gates": {
            "floor2_online_gt_0": int(dist["by_floor"].get(2, 0)) > 0,
            "top1_hotspot_ratio_lt_0_40": top1_ratio < 0.4,
            "top1_hotspot_ratio": top1_ratio,
        },
    }
