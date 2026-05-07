"""
affinityengine - Maintain the dynamic balance of friend relationships
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_friendship import AgentFriendship

logger = logging.getLogger(__name__)

# Attenuation parameter
DECAY_INACTIVE_DAYS = 3       # After this number of days without interaction, it will begin to decay.
DECAY_RATE_PER_DAY = 2        # Affinity decays every day
MIN_AFFINITY = 0              # affinity lower limit
MAX_AFFINITY = 100            # affinity upper limit

# The impact of different interactions on affinity
AFFINITY_REWARDS = {
    "chat": 2,                # chat
    "task_collaborate": 5,    # Complete the collaboration task
    "event_together": 3,      # Participate in the same Activity
    "task_complete_dept": 3,  # Same as DepartmentComplete Task
    "mentor_task": 4,         # Instructor guidance task
}


def clamp_affinity(value: int) -> int:
    """Make sure affinity is within the valid range"""
    return max(MIN_AFFINITY, min(MAX_AFFINITY, value))


async def update_interaction_time(
    db: AsyncSession,
    agent_id_a: int,
    agent_id_b: int,
    interaction_type: str = "chat",
) -> int | None:
    """
    Record the interaction between two agents，Update affinity and last interaction time。

    Returns:
        Updated affinity value，If not friend then BackNone
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
    Timing Task：Perform affinity decay on long-term non-interactive friend relationships。
    It is recommended to run it once a day。
    """
    async with AsyncSessionLocal() as db:
        threshold = datetime.now(timezone.utc) - timedelta(days=DECAY_INACTIVE_DAYS)

        # Find all accepted friend relationships whose last interaction time exceeds the threshold
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
                # If the interaction time is never recorded，Counting from accepttime
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
