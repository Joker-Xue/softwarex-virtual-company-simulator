"""
achievementengine - achievement seed data, unlock check
"""
import logging
from datetime import timedelta
from sqlalchemy import select, func as sa_func, or_, distinct, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, UserAchievement
from app.models.agent_profile import AgentProfile
from app.models.agent_friendship import AgentFriendship
from app.models.agent_task import AgentTask
from app.models.coin_wallet import CoinWallet, CoinTransaction
from app.models.company_event import CompanyEvent
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Predefined achievement list ──
ACHIEVEMENT_DEFS = [
    # Task kind
    {"key": "first_task", "name": "fledgling", "description": "Complete the first Task", "category": "task", "icon": "⭐", "coin_reward": 50, "condition_type": "tasks_completed", "condition_value": 1},
    {"key": "tasks_5", "name": "small achievement", "description": "Completed 5 Tasks in total", "category": "task", "icon": "📋", "coin_reward": 80, "condition_type": "tasks_completed", "condition_value": 5},
    {"key": "tasks_10", "name": "Task expert", "description": "Completed a total of 10 Tasks", "category": "task", "icon": "📋", "coin_reward": 100, "condition_type": "tasks_completed", "condition_value": 10},
    {"key": "tasks_25", "name": "Diligent Star", "description": "Completed 25 Tasks in total", "category": "task", "icon": "🌟", "coin_reward": 150, "condition_type": "tasks_completed", "condition_value": 25},
    {"key": "tasks_50", "name": "efficiency expert", "description": "Completed a total of 50 Tasks", "category": "task", "icon": "🏅", "coin_reward": 200, "condition_type": "tasks_completed", "condition_value": 50},
    {"key": "tasks_100", "name": "Victory in every battle", "description": "Completed 100 Tasks in total", "category": "task", "icon": "💯", "coin_reward": 500, "condition_type": "tasks_completed", "condition_value": 100},
    {"key": "streak_3", "name": "three consecutive wins", "description": "Complete Task for 3 consecutive days", "category": "task", "icon": "🔥", "coin_reward": 80, "condition_type": "streak_days", "condition_value": 3},
    {"key": "streak_7", "name": "Weekly champion", "description": "Complete Task for 7 consecutive days", "category": "task", "icon": "🔥", "coin_reward": 150, "condition_type": "streak_days", "condition_value": 7},
    {"key": "streak_14", "name": "half moon star", "description": "Complete Task for 14 consecutive days", "category": "task", "icon": "🔥", "coin_reward": 300, "condition_type": "streak_days", "condition_value": 14},
    {"key": "streak_30", "name": "Legend of the Month", "description": "Complete Task for 30 consecutive days", "category": "task", "icon": "🔥", "coin_reward": 500, "condition_type": "streak_days", "condition_value": 30},
    # Social kind
    {"key": "first_friend", "name": "First acquaintance", "description": "Make your first friend", "category": "social", "icon": "🤝", "coin_reward": 50, "condition_type": "friends_count", "condition_value": 1},
    {"key": "friends_3", "name": "small circle", "description": "Have 3 friends", "category": "social", "icon": "👥", "coin_reward": 80, "condition_type": "friends_count", "condition_value": 3},
    {"key": "friends_5", "name": "Social butterfly", "description": "Have 5 friends", "category": "social", "icon": "🦋", "coin_reward": 100, "condition_type": "friends_count", "condition_value": 5},
    {"key": "friends_10", "name": "Well connected", "description": "Have 10 friends", "category": "social", "icon": "🌐", "coin_reward": 200, "condition_type": "friends_count", "condition_value": 10},
    {"key": "friends_20", "name": "King of Social", "description": "Have 20 friends", "category": "social", "icon": "👑", "coin_reward": 400, "condition_type": "friends_count", "condition_value": 20},
    {"key": "max_affinity", "name": "best friend", "description": "Reach 100 friendaffinity with someone", "category": "social", "icon": "❤️", "coin_reward": 200, "condition_type": "max_affinity", "condition_value": 100},
    # Career kind
    {"key": "first_promotion", "name": "promotion step by step", "description": "gain first promotion", "category": "career", "icon": "📈", "coin_reward": 100, "condition_type": "career_level", "condition_value": 1},
    {"key": "reach_mid", "name": "mainstay", "description": "promoted toMid-level Staff", "category": "career", "icon": "📊", "coin_reward": 150, "condition_type": "career_level", "condition_value": 2},
    {"key": "reach_senior", "name": "stand alone", "description": "promoted toSenior Staff", "category": "career", "icon": "💼", "coin_reward": 200, "condition_type": "career_level", "condition_value": 3},
    {"key": "reach_manager", "name": "Talent of management", "description": "promoted toManager", "category": "career", "icon": "🏢", "coin_reward": 300, "condition_type": "career_level", "condition_value": 4},
    {"key": "reach_director", "name": "strategizing", "description": "promoted toDirector", "category": "career", "icon": "🏛️", "coin_reward": 500, "condition_type": "career_level", "condition_value": 5},
    {"key": "reach_ceo", "name": "Reach the pinnacle", "description": "promoted toCEO", "category": "career", "icon": "👔", "coin_reward": 1000, "condition_type": "career_level", "condition_value": 6},
    # Economy kind
    {"key": "coins_500", "name": "Small savings", "description": "Accumulated gain 500 gold coins", "category": "economy", "icon": "💰", "coin_reward": 50, "condition_type": "coins_earned", "condition_value": 500},
    {"key": "coins_1000", "name": "Reward of Thousands of Gold", "description": "Accumulated gain1000 gold coins", "category": "economy", "icon": "💰", "coin_reward": 100, "condition_type": "coins_earned", "condition_value": 1000},
    {"key": "coins_5000", "name": "The richest party", "description": "Accumulated gain 5000 gold coins", "category": "economy", "icon": "💎", "coin_reward": 200, "condition_type": "coins_earned", "condition_value": 5000},
    {"key": "coins_10000", "name": "Vast wealth", "description": "Accumulated gain10000 gold coins", "category": "economy", "icon": "💎", "coin_reward": 500, "condition_type": "coins_earned", "condition_value": 10000},
    # Explore kind
    {"key": "first_event", "name": "first time participation", "description": "Participate in the first company activity", "category": "explore", "icon": "🎉", "coin_reward": 50, "condition_type": "events_joined", "condition_value": 1},
    {"key": "events_5", "name": "Activity activist", "description": "Participated in 5 company activities", "category": "explore", "icon": "🎊", "coin_reward": 100, "condition_type": "events_joined", "condition_value": 5},
    {"key": "events_10", "name": "Activity star", "description": "Participated in 10 company activities", "category": "explore", "icon": "🌟", "coin_reward": 200, "condition_type": "events_joined", "condition_value": 10},
    {"key": "visit_all_rooms", "name": "explorer", "description": "Access to all company rooms", "category": "explore", "icon": "🗺️", "coin_reward": 150, "condition_type": "rooms_visited", "condition_value": 1, "is_hidden": True},
    {"key": "xp_500", "name": "Experienced", "description": "Accumulated gain500 experience points", "category": "explore", "icon": "📖", "coin_reward": 100, "condition_type": "xp_earned", "condition_value": 500},
    {"key": "xp_2000", "name": "knowledgeable", "description": "Accumulated gain2000 experience points", "category": "explore", "icon": "📚", "coin_reward": 200, "condition_type": "xp_earned", "condition_value": 2000},
]


async def seed_achievements() -> None:
    """Seed achievement data into Database"""
    async with AsyncSessionLocal() as db:
        for ach_def in ACHIEVEMENT_DEFS:
            result = await db.execute(
                select(Achievement).where(Achievement.key == ach_def["key"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                ach = Achievement(
                    key=ach_def["key"],
                    name=ach_def["name"],
                    description=ach_def["description"],
                    category=ach_def["category"],
                    icon=ach_def["icon"],
                    coin_reward=ach_def["coin_reward"],
                    condition_type=ach_def["condition_type"],
                    condition_value=ach_def["condition_value"],
                    is_hidden=ach_def.get("is_hidden", False),
                )
                db.add(ach)
        await db.commit()
    logger.info("Achievement seed data initialization completed，Total %d msgs definitions", len(ACHIEVEMENT_DEFS))


async def _get_agent_stat(db: AsyncSession, agent_id: int, condition_type: str) -> int:
    """Get a certain statistical value of Agent"""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return 0

    if condition_type == "tasks_completed":
        return profile.tasks_completed or 0

    elif condition_type == "career_level":
        return profile.career_level or 0

    elif condition_type == "xp_earned":
        return profile.xp or 0

    elif condition_type == "friends_count":
        count_result = await db.execute(
            select(sa_func.count(AgentFriendship.id)).where(
                or_(
                    AgentFriendship.from_id == agent_id,
                    AgentFriendship.to_id == agent_id,
                ),
                AgentFriendship.status == "accepted",
            )
        )
        return count_result.scalar() or 0

    elif condition_type == "max_affinity":
        aff_result = await db.execute(
            select(sa_func.max(AgentFriendship.affinity)).where(
                or_(
                    AgentFriendship.from_id == agent_id,
                    AgentFriendship.to_id == agent_id,
                ),
                AgentFriendship.status == "accepted",
            )
        )
        return aff_result.scalar() or 0

    elif condition_type == "coins_earned":
        wallet_result = await db.execute(
            select(CoinWallet).where(CoinWallet.user_id == profile.user_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        return wallet.total_earned if wallet else 0

    elif condition_type == "streak_days":
        # Calculate the number of days of consecutive Complete Tasks：Counting backward from the most recent day
        days_result = await db.execute(
            select(distinct(cast(AgentTask.completed_at, Date)))
            .where(
                AgentTask.assignee_id == agent_id,
                AgentTask.status == "completed",
                AgentTask.completed_at.is_not(None),
            )
            .order_by(cast(AgentTask.completed_at, Date).desc())
            .limit(60)
        )
        dates = [row[0] for row in days_result.fetchall()]
        if not dates:
            return 0
        streak = 1
        for i in range(1, len(dates)):
            if dates[i - 1] - dates[i] == timedelta(days=1):
                streak += 1
            else:
                break
        return streak

    elif condition_type == "events_joined":
        # Join in statistics action_log number of events（actionThe field contains activity types such as meetings）
        from app.models.agent_action_log import AgentActionLog
        event_result = await db.execute(
            select(sa_func.count(AgentActionLog.id)).where(
                AgentActionLog.agent_id == agent_id,
                AgentActionLog.action == "meeting",
            )
        )
        return event_result.scalar() or 0

    elif condition_type == "rooms_visited":
        # Statistics of different rooms visited（Deduplication through location field）
        from app.models.agent_action_log import AgentActionLog
        from app.models.company_room import CompanyRoom
        visited_result = await db.execute(
            select(sa_func.count(distinct(AgentActionLog.location))).where(
                AgentActionLog.agent_id == agent_id,
                AgentActionLog.location.is_not(None),
            )
        )
        visited_count = visited_result.scalar() or 0
        total_rooms_result = await db.execute(
            select(sa_func.count(CompanyRoom.id))
        )
        total_rooms = total_rooms_result.scalar() or 1
        # Back 1 If all rooms have been visited，Otherwise 0
        return 1 if visited_count >= total_rooms and total_rooms > 0 else 0

    return 0


async def check_achievements(
    db: AsyncSession,
    agent_id: int,
    event_type: str,
    **kwargs,
) -> list[dict]:
    """
    Check and unlock new achievements。

    Args:
        db: Databasesession
        agent_id: Agent ID
        event_type: Trigger event type (task_complete/friendship/promotion/economy/explore)

    Returns:
        List of newly unlocked achievements
    """
    # event typeFilter achievements that need to be checked condition_type
    event_to_conditions = {
        "task_complete": ["tasks_completed", "streak_days"],
        "friendship": ["friends_count", "max_affinity"],
        "promotion": ["career_level"],
        "economy": ["coins_earned"],
        "explore": ["events_joined", "rooms_visited"],
        "xp_gain": ["xp_earned"],
    }
    condition_types = event_to_conditions.get(event_type, [])
    # if event typeUnknown，check all
    if not condition_types:
        condition_types = [
            "tasks_completed", "friends_count", "career_level",
            "coins_earned", "rooms_visited", "streak_days",
            "events_joined", "max_affinity", "xp_earned",
        ]

    # Query related achievements
    result = await db.execute(
        select(Achievement).where(Achievement.condition_type.in_(condition_types))
    )
    achievements = result.scalars().all()

    # Achievement unlocked
    unlocked_result = await db.execute(
        select(UserAchievement.achievement_id).where(
            UserAchievement.agent_id == agent_id,
        )
    )
    unlocked_ids = {row[0] for row in unlocked_result.fetchall()}

    newly_unlocked = []

    for ach in achievements:
        if ach.id in unlocked_ids:
            continue

        current_value = await _get_agent_stat(db, agent_id, ach.condition_type)
        if current_value >= ach.condition_value:
            # Unlock achievements
            ua = UserAchievement(agent_id=agent_id, achievement_id=ach.id)
            db.add(ua)

            # Issue gold coin rewards
            profile_result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == agent_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile and ach.coin_reward > 0:
                wallet_result = await db.execute(
                    select(CoinWallet).where(CoinWallet.user_id == profile.user_id)
                )
                wallet = wallet_result.scalar_one_or_none()
                if wallet:
                    wallet.balance += ach.coin_reward
                    wallet.total_earned += ach.coin_reward
                    db.add(CoinTransaction(
                        user_id=profile.user_id,
                        amount=ach.coin_reward,
                        type="earn",
                        source="achievement",
                        description=f"Unlock achievements「{ach.name}」",
                    ))

            newly_unlocked.append({
                "id": ach.id,
                "key": ach.key,
                "name": ach.name,
                "description": ach.description,
                "icon": ach.icon,
                "coin_reward": ach.coin_reward,
            })

            logger.info("achievement unlocked: agent=%d achievement=%s", agent_id, ach.key)

    if newly_unlocked:
        await db.flush()

    return newly_unlocked


async def get_achievement_progress(db: AsyncSession, agent_id: int) -> list[dict]:
    """
    Get the progress information of all achievements。

    Returns:
        A list containing all achievements and their progress
    """
    result = await db.execute(select(Achievement).order_by(Achievement.category, Achievement.condition_value))
    achievements = result.scalars().all()

    unlocked_result = await db.execute(
        select(UserAchievement).where(UserAchievement.agent_id == agent_id)
    )
    unlocked_map = {ua.achievement_id: ua for ua in unlocked_result.scalars().all()}

    progress_list = []
    # Cachestat query results
    stat_cache: dict[str, int] = {}

    for ach in achievements:
        is_unlocked = ach.id in unlocked_map
        ua = unlocked_map.get(ach.id)

        if ach.condition_type not in stat_cache:
            stat_cache[ach.condition_type] = await _get_agent_stat(db, agent_id, ach.condition_type)

        current_value = stat_cache[ach.condition_type]
        progress = min(1.0, current_value / ach.condition_value) if ach.condition_value > 0 else 0.0

        progress_list.append({
            "id": ach.id,
            "key": ach.key,
            "name": ach.name,
            "description": ach.description,
            "category": ach.category,
            "icon": ach.icon,
            "coin_reward": ach.coin_reward,
            "is_hidden": ach.is_hidden,
            "is_unlocked": is_unlocked,
            "unlocked_at": ua.unlocked_at.isoformat() if ua and ua.unlocked_at else None,
            "progress": round(progress, 2),
            "current_value": current_value,
            "target_value": ach.condition_value,
        })

    return progress_list
