"""
任务系统API
"""
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func as sa_func

from app.database import get_db
from app.utils.security import get_current_active_user
from app.utils.rate_limit import check_rate_limit
from app.utils.sanitize import clamp_affinity
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.agent_friendship import AgentFriendship
from app.models.coin_wallet import CoinWallet, CoinTransaction
from app.schemas.agent_social import TaskAssign, TaskOut, LeaderboardEntry, CAREER_LEVELS
from app.engine.memory_engine import extract_memory
from app.engine.task_generator import generate_tasks_for_agent
from app.engine.achievement_engine import check_achievements

router = APIRouter()


def _check_promotion(profile: AgentProfile) -> int | None:
    """检查是否满足晋升条件，返回新等级或None"""
    next_level = profile.career_level + 1
    if next_level > 6:
        return None
    req = CAREER_LEVELS[next_level]
    if profile.tasks_completed >= req["tasks_required"] and profile.xp >= req["xp_required"]:
        return next_level
    return None


async def complete_task_internal(
    db: AsyncSession, profile: AgentProfile, task, coin_wallet=None
) -> dict:
    """内部任务完成逻辑，供模拟引擎和HTTP端点共用。不依赖HTTP上下文。"""
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    profile.tasks_completed += 1
    profile.xp += task.xp_reward

    coin_reward = task.xp_reward

    # 检查晋升
    new_level = _check_promotion(profile)
    promotion = None
    if new_level is not None:
        profile.career_level = new_level
        promotion = {
            "new_level": new_level,
            "title": CAREER_LEVELS[new_level]["title"],
        }

    await db.flush()

    # 提取任务完成记忆
    await extract_memory(
        db, profile.id, "task_complete",
        "完成了任务「" + task.title + "」，获得" + str(task.xp_reward) + "XP",
    )
    if promotion:
        await extract_memory(
            db, profile.id, "promotion",
            "晋升为" + promotion["title"] + "（等级" + str(promotion["new_level"]) + "）",
        )

    return {
        "task_id": task.id,
        "xp_earned": task.xp_reward,
        "coin_earned": coin_reward,
        "promotion": promotion,
    }


@router.get("/my", response_model=list[TaskOut], summary="我的任务列表")
async def my_tasks(
    status: str = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    q = select(AgentTask).where(AgentTask.assignee_id == profile.id)
    if status:
        q = q.where(AgentTask.status == status)
    q = q.order_by(AgentTask.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/assign", response_model=TaskOut, summary="上级派发任务")
async def assign_task(
    body: TaskAssign,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 限流：每用户每小时10次
    await check_rate_limit(f"assign:{user.id}", max_calls=10, window_seconds=3600)
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    assigner = result.scalar_one_or_none()
    if not assigner or assigner.career_level < 4:
        raise HTTPException(403, "需要经理及以上职级才能派发任务")

    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == body.assignee_id)
    )
    assignee = result.scalar_one_or_none()
    if not assignee:
        raise HTTPException(404, "目标角色不存在")

    xp_reward = body.difficulty * 15
    task = AgentTask(
        title=body.title,
        description=body.description,
        task_type=body.task_type,
        difficulty=body.difficulty,
        xp_reward=xp_reward,
        assigner_id=assigner.id,
        assignee_id=body.assignee_id,
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.post("/generate", response_model=list[TaskOut], summary="生成每日任务")
async def generate_daily_tasks(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 限流：每用户每小时5次
    await check_rate_limit(f"generate:{user.id}", max_calls=5, window_seconds=3600)
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    tasks = await generate_tasks_for_agent(profile, db)
    await db.flush()
    for task in tasks:
        await db.refresh(task)
    return tasks


@router.post("/{task_id}/complete", summary="完成任务")
async def complete_task(
    task_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    result = await db.execute(
        select(AgentTask).where(AgentTask.id == task_id, AgentTask.assignee_id == profile.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status == "completed":
        raise HTTPException(400, "任务已完成")

    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    profile.tasks_completed += 1
    profile.xp += task.xp_reward

    # 金币奖励
    coin_reward = task.xp_reward
    wallet_result = await db.execute(
        select(CoinWallet).where(CoinWallet.user_id == user.id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if wallet:
        wallet.balance += coin_reward
        wallet.total_earned += coin_reward
        db.add(CoinTransaction(
            user_id=user.id, amount=coin_reward, type="earn",
            source="agent_task", description=f"完成任务: {task.title}",
        ))

    # 检查晋升
    new_level = _check_promotion(profile)
    promotion = None
    if new_level is not None:
        profile.career_level = new_level
        promotion = {
            "new_level": new_level,
            "title": CAREER_LEVELS[new_level]["title"],
        }
        # 晋升金币奖励
        promo_coins = new_level * 100
        if wallet:
            wallet.balance += promo_coins
            wallet.total_earned += promo_coins
            db.add(CoinTransaction(
                user_id=user.id, amount=promo_coins, type="earn",
                source="agent_promotion", description=f"晋升为{CAREER_LEVELS[new_level]['title']}",
            ))

    await db.flush()

    # 提取任务完成记忆
    await extract_memory(
        db, profile.id, "task_complete",
        f"完成了任务「{task.title}」，获得{task.xp_reward}XP",
    )

    # 如果触发晋升，提取晋升记忆
    if promotion:
        await extract_memory(
            db, profile.id, "promotion",
            f"晋升为{promotion['title']}（等级{promotion['new_level']}）",
        )

    # 完成任务后，增加同部门好友的亲密度 +3
    friend_result = await db.execute(
        select(AgentFriendship).where(
            or_(
                AgentFriendship.from_id == profile.id,
                AgentFriendship.to_id == profile.id,
            ),
            AgentFriendship.status == "accepted",
        )
    )
    friendships = friend_result.scalars().all()
    for fs in friendships:
        friend_agent_id = fs.to_id if fs.from_id == profile.id else fs.from_id
        # 查询好友的profile，判断是否同部门
        friend_profile_result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == friend_agent_id)
        )
        friend_profile = friend_profile_result.scalar_one_or_none()
        if friend_profile and friend_profile.department == profile.department:
            fs.affinity = clamp_affinity((fs.affinity or 50) + 3)
    await db.flush()

    # 检查成就解锁（任务完成 + 经验值 + 经济）
    new_achievements = await check_achievements(db, profile.id, "task_complete")
    new_achievements += await check_achievements(db, profile.id, "xp_gain")
    new_achievements += await check_achievements(db, profile.id, "economy")
    if promotion:
        new_achievements += await check_achievements(db, profile.id, "promotion")

    return {
        "task_id": task.id,
        "xp_earned": task.xp_reward,
        "coin_earned": coin_reward,
        "total_xp": profile.xp,
        "tasks_completed": profile.tasks_completed,
        "career_level": profile.career_level,
        "promotion": promotion,
        "new_achievements": new_achievements,
    }


@router.get("/leaderboard", response_model=list[LeaderboardEntry], summary="排行榜")
async def leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentProfile).order_by(AgentProfile.xp.desc()).limit(20)
    )
    agents = result.scalars().all()
    return [
        LeaderboardEntry(
            agent_id=a.id,
            nickname=a.nickname,
            avatar_key=a.avatar_key,
            career_level=a.career_level,
            career_title=CAREER_LEVELS.get(a.career_level, {}).get("title", "未知"),
            xp=a.xp,
            tasks_completed=a.tasks_completed,
            department=a.department,
        )
        for a in agents
    ]
