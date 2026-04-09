"""
亲密度衰减引擎 - 维护好友关系的动态平衡
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_friendship import AgentFriendship

logger = logging.getLogger(__name__)

# 衰减参数
DECAY_INACTIVE_DAYS = 3       # 超过此天数无互动开始衰减
DECAY_RATE_PER_DAY = 2        # 每天衰减的亲密度
MIN_AFFINITY = 0              # 亲密度下限
MAX_AFFINITY = 100            # 亲密度上限

# 不同互动对亲密度的影响
AFFINITY_REWARDS = {
    "chat": 2,                # 聊天
    "task_collaborate": 5,    # 完成协作任务
    "event_together": 3,      # 参加同一活动
    "task_complete_dept": 3,  # 同部门完成任务
    "mentor_task": 4,         # 导师指导任务
}


def clamp_affinity(value: int) -> int:
    """确保亲密度在有效范围内"""
    return max(MIN_AFFINITY, min(MAX_AFFINITY, value))


async def update_interaction_time(
    db: AsyncSession,
    agent_id_a: int,
    agent_id_b: int,
    interaction_type: str = "chat",
) -> int | None:
    """
    记录两个Agent之间的互动，更新亲密度和最后互动时间。

    Returns:
        更新后的亲密度值，如果不是好友则返回None
    """
    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.status == "accepted",
            or_(
                and_(AgentFriendship.from_id == agent_id_a, AgentFriendship.to_id == agent_id_b),
                and_(AgentFriendship.from_id == agent_id_b, AgentFriendship.to_id == agent_id_a),
            ),
        )
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        return None

    reward = AFFINITY_REWARDS.get(interaction_type, 2)
    friendship.affinity = clamp_affinity((friendship.affinity or 50) + reward)
    friendship.last_interaction_at = datetime.now(timezone.utc)

    return friendship.affinity


async def run_affinity_decay():
    """
    定时任务：对长期无互动的好友关系执行亲密度衰减。
    建议每天运行一次。
    """
    async with AsyncSessionLocal() as db:
        threshold = datetime.now(timezone.utc) - timedelta(days=DECAY_INACTIVE_DAYS)

        # 查找所有已接受且最后互动时间超过阈值的好友关系
        result = await db.execute(
            select(AgentFriendship).where(
                AgentFriendship.status == "accepted",
                or_(
                    AgentFriendship.last_interaction_at < threshold,
                    AgentFriendship.last_interaction_at.is_(None),
                ),
                AgentFriendship.affinity > MIN_AFFINITY,
            )
        )
        friendships = result.scalars().all()

        decayed_count = 0
        for fs in friendships:
            if fs.last_interaction_at:
                days_inactive = (datetime.now(timezone.utc) - fs.last_interaction_at).days
            else:
                # 如果从未记录互动时间，从接受时间算起
                if fs.accepted_at:
                    days_inactive = (datetime.now(timezone.utc) - fs.accepted_at).days
                else:
                    days_inactive = DECAY_INACTIVE_DAYS + 1

            if days_inactive > DECAY_INACTIVE_DAYS:
                decay_amount = DECAY_RATE_PER_DAY
                old_affinity = fs.affinity or 50
                fs.affinity = clamp_affinity(old_affinity - decay_amount)
                decayed_count += 1

        await db.commit()
        logger.info("Affinity decay completed: %d friendships decayed", decayed_count)
        return decayed_count
