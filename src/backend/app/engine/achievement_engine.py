"""
成就引擎 - 成就种子数据、解锁检查
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

# ── 预定义成就列表 ──
ACHIEVEMENT_DEFS = [
    # Task 类
    {"key": "first_task", "name": "初出茅庐", "description": "完成第一个任务", "category": "task", "icon": "⭐", "coin_reward": 50, "condition_type": "tasks_completed", "condition_value": 1},
    {"key": "tasks_5", "name": "小有成就", "description": "累计完成5个任务", "category": "task", "icon": "📋", "coin_reward": 80, "condition_type": "tasks_completed", "condition_value": 5},
    {"key": "tasks_10", "name": "任务达人", "description": "累计完成10个任务", "category": "task", "icon": "📋", "coin_reward": 100, "condition_type": "tasks_completed", "condition_value": 10},
    {"key": "tasks_25", "name": "勤勉之星", "description": "累计完成25个任务", "category": "task", "icon": "🌟", "coin_reward": 150, "condition_type": "tasks_completed", "condition_value": 25},
    {"key": "tasks_50", "name": "效率专家", "description": "累计完成50个任务", "category": "task", "icon": "🏅", "coin_reward": 200, "condition_type": "tasks_completed", "condition_value": 50},
    {"key": "tasks_100", "name": "百战百胜", "description": "累计完成100个任务", "category": "task", "icon": "💯", "coin_reward": 500, "condition_type": "tasks_completed", "condition_value": 100},
    {"key": "streak_3", "name": "三连胜", "description": "连续3天完成任务", "category": "task", "icon": "🔥", "coin_reward": 80, "condition_type": "streak_days", "condition_value": 3},
    {"key": "streak_7", "name": "周冠军", "description": "连续7天完成任务", "category": "task", "icon": "🔥", "coin_reward": 150, "condition_type": "streak_days", "condition_value": 7},
    {"key": "streak_14", "name": "半月之星", "description": "连续14天完成任务", "category": "task", "icon": "🔥", "coin_reward": 300, "condition_type": "streak_days", "condition_value": 14},
    {"key": "streak_30", "name": "月度传奇", "description": "连续30天完成任务", "category": "task", "icon": "🔥", "coin_reward": 500, "condition_type": "streak_days", "condition_value": 30},
    # Social 类
    {"key": "first_friend", "name": "初识", "description": "结交第一个好友", "category": "social", "icon": "🤝", "coin_reward": 50, "condition_type": "friends_count", "condition_value": 1},
    {"key": "friends_3", "name": "小圈子", "description": "拥有3位好友", "category": "social", "icon": "👥", "coin_reward": 80, "condition_type": "friends_count", "condition_value": 3},
    {"key": "friends_5", "name": "社交蝴蝶", "description": "拥有5位好友", "category": "social", "icon": "🦋", "coin_reward": 100, "condition_type": "friends_count", "condition_value": 5},
    {"key": "friends_10", "name": "人脉广泛", "description": "拥有10位好友", "category": "social", "icon": "🌐", "coin_reward": 200, "condition_type": "friends_count", "condition_value": 10},
    {"key": "friends_20", "name": "社交之王", "description": "拥有20位好友", "category": "social", "icon": "👑", "coin_reward": 400, "condition_type": "friends_count", "condition_value": 20},
    {"key": "max_affinity", "name": "挚友", "description": "与某位好友亲密度达到100", "category": "social", "icon": "❤️", "coin_reward": 200, "condition_type": "max_affinity", "condition_value": 100},
    # Career 类
    {"key": "first_promotion", "name": "步步高升", "description": "获得第一次晋升", "category": "career", "icon": "📈", "coin_reward": 100, "condition_type": "career_level", "condition_value": 1},
    {"key": "reach_mid", "name": "中流砥柱", "description": "晋升为中级员工", "category": "career", "icon": "📊", "coin_reward": 150, "condition_type": "career_level", "condition_value": 2},
    {"key": "reach_senior", "name": "独当一面", "description": "晋升为高级员工", "category": "career", "icon": "💼", "coin_reward": 200, "condition_type": "career_level", "condition_value": 3},
    {"key": "reach_manager", "name": "管理之才", "description": "晋升为经理", "category": "career", "icon": "🏢", "coin_reward": 300, "condition_type": "career_level", "condition_value": 4},
    {"key": "reach_director", "name": "运筹帷幄", "description": "晋升为总监", "category": "career", "icon": "🏛️", "coin_reward": 500, "condition_type": "career_level", "condition_value": 5},
    {"key": "reach_ceo", "name": "登峰造极", "description": "晋升为CEO", "category": "career", "icon": "👔", "coin_reward": 1000, "condition_type": "career_level", "condition_value": 6},
    # Economy 类
    {"key": "coins_500", "name": "小有积蓄", "description": "累计获得500金币", "category": "economy", "icon": "💰", "coin_reward": 50, "condition_type": "coins_earned", "condition_value": 500},
    {"key": "coins_1000", "name": "千金之赏", "description": "累计获得1000金币", "category": "economy", "icon": "💰", "coin_reward": 100, "condition_type": "coins_earned", "condition_value": 1000},
    {"key": "coins_5000", "name": "富甲一方", "description": "累计获得5000金币", "category": "economy", "icon": "💎", "coin_reward": 200, "condition_type": "coins_earned", "condition_value": 5000},
    {"key": "coins_10000", "name": "万贯家财", "description": "累计获得10000金币", "category": "economy", "icon": "💎", "coin_reward": 500, "condition_type": "coins_earned", "condition_value": 10000},
    # Explore 类
    {"key": "first_event", "name": "初次参与", "description": "参加第一次公司活动", "category": "explore", "icon": "🎉", "coin_reward": 50, "condition_type": "events_joined", "condition_value": 1},
    {"key": "events_5", "name": "活动积极分子", "description": "参加5次公司活动", "category": "explore", "icon": "🎊", "coin_reward": 100, "condition_type": "events_joined", "condition_value": 5},
    {"key": "events_10", "name": "活动之星", "description": "参加10次公司活动", "category": "explore", "icon": "🌟", "coin_reward": 200, "condition_type": "events_joined", "condition_value": 10},
    {"key": "visit_all_rooms", "name": "探索者", "description": "访问公司所有房间", "category": "explore", "icon": "🗺️", "coin_reward": 150, "condition_type": "rooms_visited", "condition_value": 1, "is_hidden": True},
    {"key": "xp_500", "name": "经验丰富", "description": "累计获得500经验值", "category": "explore", "icon": "📖", "coin_reward": 100, "condition_type": "xp_earned", "condition_value": 500},
    {"key": "xp_2000", "name": "学识渊博", "description": "累计获得2000经验值", "category": "explore", "icon": "📚", "coin_reward": 200, "condition_type": "xp_earned", "condition_value": 2000},
]


async def seed_achievements() -> None:
    """种子成就数据到数据库"""
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
    logger.info("成就种子数据初始化完成，共%d条定义", len(ACHIEVEMENT_DEFS))


async def _get_agent_stat(db: AsyncSession, agent_id: int, condition_type: str) -> int:
    """获取Agent的某项统计数值"""
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
        # 计算连续完成任务的天数：从最近一天往回数
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
        # 统计action_log中参加活动的次数（action字段包含meeting等活动类型）
        from app.models.agent_action_log import AgentActionLog
        event_result = await db.execute(
            select(sa_func.count(AgentActionLog.id)).where(
                AgentActionLog.agent_id == agent_id,
                AgentActionLog.action == "meeting",
            )
        )
        return event_result.scalar() or 0

    elif condition_type == "rooms_visited":
        # 统计访问过的不同房间（通过location字段去重）
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
        # 返回 1 如果已访问全部房间，否则 0
        return 1 if visited_count >= total_rooms and total_rooms > 0 else 0

    return 0


async def check_achievements(
    db: AsyncSession,
    agent_id: int,
    event_type: str,
    **kwargs,
) -> list[dict]:
    """
    检查并解锁新成就。

    Args:
        db: 数据库会话
        agent_id: Agent ID
        event_type: 触发事件类型 (task_complete/friendship/promotion/economy/explore)

    Returns:
        新解锁的成就列表
    """
    # 根据事件类型过滤需要检查的成就 condition_type
    event_to_conditions = {
        "task_complete": ["tasks_completed", "streak_days"],
        "friendship": ["friends_count", "max_affinity"],
        "promotion": ["career_level"],
        "economy": ["coins_earned"],
        "explore": ["events_joined", "rooms_visited"],
        "xp_gain": ["xp_earned"],
    }
    condition_types = event_to_conditions.get(event_type, [])
    # 如果事件类型未知，检查所有
    if not condition_types:
        condition_types = [
            "tasks_completed", "friends_count", "career_level",
            "coins_earned", "rooms_visited", "streak_days",
            "events_joined", "max_affinity", "xp_earned",
        ]

    # 查询相关成就
    result = await db.execute(
        select(Achievement).where(Achievement.condition_type.in_(condition_types))
    )
    achievements = result.scalars().all()

    # 已解锁成就
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
            # 解锁成就
            ua = UserAchievement(agent_id=agent_id, achievement_id=ach.id)
            db.add(ua)

            # 发放金币奖励
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
                        description=f"解锁成就「{ach.name}」",
                    ))

            newly_unlocked.append({
                "id": ach.id,
                "key": ach.key,
                "name": ach.name,
                "description": ach.description,
                "icon": ach.icon,
                "coin_reward": ach.coin_reward,
            })

            logger.info("成就解锁: agent=%d achievement=%s", agent_id, ach.key)

    if newly_unlocked:
        await db.flush()

    return newly_unlocked


async def get_achievement_progress(db: AsyncSession, agent_id: int) -> list[dict]:
    """
    获取所有成就的进度信息。

    Returns:
        包含所有成就及其进度的列表
    """
    result = await db.execute(select(Achievement).order_by(Achievement.category, Achievement.condition_value))
    achievements = result.scalars().all()

    unlocked_result = await db.execute(
        select(UserAchievement).where(UserAchievement.agent_id == agent_id)
    )
    unlocked_map = {ua.achievement_id: ua for ua in unlocked_result.scalars().all()}

    progress_list = []
    # 缓存stat查询结果
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
