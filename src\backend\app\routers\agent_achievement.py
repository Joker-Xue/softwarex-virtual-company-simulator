"""
成就系统API
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


@router.get("/list", response_model=list[AchievementOut], summary="全部成就列表（含解锁状态）")
async def list_achievements(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """列出所有成就，标注当前用户的解锁状态和进度"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    progress_list = await get_achievement_progress(db, profile.id)

    return [
        AchievementOut(
            id=p["id"],
            key=p["key"],
            name=p["name"] if not p["is_hidden"] or p["is_unlocked"] else "???",
            description=p["description"] if not p["is_hidden"] or p["is_unlocked"] else "隐藏成就，完成后揭晓",
            category=p["category"],
            icon=p["icon"] if not p["is_hidden"] or p["is_unlocked"] else "❓",
            coin_reward=p["coin_reward"],
            is_unlocked=p["is_unlocked"],
            unlocked_at=p["unlocked_at"],
            progress=p["progress"],
        )
        for p in progress_list
    ]


@router.get("/my", response_model=list[AchievementOut], summary="我的已解锁成就")
async def my_achievements(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户已解锁的成就"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

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


@router.get("/progress", summary="成就进度详情")
async def achievement_progress(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有成就的详细进度"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    progress_list = await get_achievement_progress(db, profile.id)

    # 按分类分组
    categories: dict[str, list] = {}
    for p in progress_list:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "id": p["id"],
            "key": p["key"],
            "name": p["name"] if not p["is_hidden"] or p["is_unlocked"] else "???",
            "description": p["description"] if not p["is_hidden"] or p["is_unlocked"] else "隐藏成就",
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
