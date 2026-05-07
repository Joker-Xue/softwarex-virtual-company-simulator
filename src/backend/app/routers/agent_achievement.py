"""
achievementSystem API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.achievement import Achievement, UserAchievement
from app.schemas.agent_social import AchievementOut
from app.engine.achievement_engine import get_achievement_progress, check_achievements

router = APIRouter()


@router.get("/list", response_model=list[AchievementOut], summary="List of all achievements（Contains unlock state）")
async def list_achievements(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all achievements，Mark Current User's unlocking state and progress"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")

    progress_list = await get_achievement_progress(db, profile.id)

    return [
        AchievementOut(
            id=p["id"],
            key=p["key"],
            name=p["name"] if not p["is_hidden"] or p["is_unlocked"] else "???",
            description=p["description"] if not p["is_hidden"] or p["is_unlocked"] else "Hide achievements，Revealed upon completion",
            category=p["category"],
            icon=p["icon"] if not p["is_hidden"] or p["is_unlocked"] else "❓",
            coin_reward=p["coin_reward"],
            is_unlocked=p["is_unlocked"],
            unlocked_at=p["unlocked_at"],
            progress=p["progress"],
        )
        for p in progress_list
    ]


@router.get("/my", response_model=list[AchievementOut], summary="My unlocked achievements")
async def my_achievements(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List Current UserUnlocked achievements"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")

    progress_list = await get_achievement_progress(db, profile.id)

    return [
        AchievementOut(
            id=p["id"],
            key=p["key"],
            name=p["name"],
            description=p["description"],
            category=p["category"],
            icon=p["icon"],
            coin_reward=p["coin_reward"],
            is_unlocked=True,
            unlocked_at=p["unlocked_at"],
            progress=1.0,
        )
        for p in progress_list
        if p["is_unlocked"]
    ]


@router.get("/progress", summary="achievement progress details")
async def achievement_progress(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed progress of all achievements"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")

    progress_list = await get_achievement_progress(db, profile.id)

    # Group by category
    categories: dict[str, list] = {}
    for p in progress_list:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "id": p["id"],
            "key": p["key"],
            "name": p["name"] if not p["is_hidden"] or p["is_unlocked"] else "???",
            "description": p["description"] if not p["is_hidden"] or p["is_unlocked"] else "Hide achievements",
            "icon": p["icon"] if not p["is_hidden"] or p["is_unlocked"] else "❓",
            "coin_reward": p["coin_reward"],
            "is_unlocked": p["is_unlocked"],
            "unlocked_at": p["unlocked_at"],
            "progress": p["progress"],
            "current_value": p["current_value"],
            "target_value": p["target_value"],
        })

    total = len(progress_list)
    unlocked = sum(1 for p in progress_list if p["is_unlocked"])

    return {
        "total_achievements": total,
        "unlocked_count": unlocked,
        "completion_rate": round(unlocked / total, 2) if total > 0 else 0.0,
        "categories": categories,
    }
