"""
动态事件引擎 - 基于公司指标自动触发事件
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.company_event import CompanyEvent

logger = logging.getLogger(__name__)

# 里程碑XP阈值
XP_MILESTONES = [1000, 5000, 10000, 25000, 50000, 100000]


def _initial_event_state(scheduled_at: datetime, now: datetime | None = None) -> str:
    """Only allow upcoming/ongoing/finished event states."""
    now = now or datetime.now(timezone.utc)
    return "ongoing" if scheduled_at <= now else "upcoming"


async def check_dynamic_events():
    """检查并触发动态事件（每小时运行一次）"""
    async with AsyncSessionLocal() as db:
        triggered = []

        # ── 1. 公司总XP里程碑 ──
        total_xp_result = await db.execute(
            select(sa_func.sum(AgentProfile.xp))
        )
        total_xp = total_xp_result.scalar() or 0

        for milestone in XP_MILESTONES:
            if total_xp >= milestone:
                # 检查是否已触发过该里程碑事件
                existing = await db.execute(
                    select(CompanyEvent).where(
                        CompanyEvent.name == f"公司里程碑：{milestone}XP",
                        CompanyEvent.event_type == "milestone",
                    )
                )
                if not existing.scalar_one_or_none():
                    scheduled_at = datetime.now(timezone.utc)
                    event = CompanyEvent(
                        name=f"公司里程碑：{milestone}XP",
                        event_type="milestone",
                        description=f"公司总经验值突破{milestone}！全员庆祝，参与可获得额外奖励！",
                        scheduled_at=scheduled_at,
                        duration_minutes=120,
                        max_participants=999,
                        rewards_xp=50,
                        rewards_coins=100,
                        is_active=_initial_event_state(scheduled_at),
                    )
                    db.add(event)
                    triggered.append(f"milestone_{milestone}")

        # ── 2. 优秀部门表彰（本周产出最高）──
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        dept_tasks_result = await db.execute(
            select(
                AgentProfile.department,
                sa_func.count(AgentTask.id).label("task_count"),
            )
            .join(AgentProfile, AgentTask.assignee_id == AgentProfile.id)
            .where(
                AgentTask.status == "completed",
                AgentTask.completed_at >= week_ago,
            )
            .group_by(AgentProfile.department)
            .order_by(sa_func.count(AgentTask.id).desc())
        )
        top_dept_row = dept_tasks_result.first()
        if top_dept_row and top_dept_row.task_count >= 5:
            dept_name = top_dept_row.department
            # 每周只触发一次
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.event_type == "dept_award",
                    CompanyEvent.scheduled_at >= week_ago,
                )
            )
            if not existing.scalar_one_or_none():
                dept_labels = {
                    "engineering": "工程部",
                    "marketing": "市场部",
                    "finance": "财务部",
                    "hr": "HR部门",
                }
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name=f"优秀部门：{dept_labels.get(dept_name, dept_name)}",
                    event_type="dept_award",
                    description=f"{dept_labels.get(dept_name, dept_name)}本周产出最高（{top_dept_row.task_count}个任务），全员表彰！",
                    scheduled_at=scheduled_at,
                    duration_minutes=60,
                    max_participants=999,
                    rewards_xp=30,
                    rewards_coins=50,
                    is_active=_initial_event_state(scheduled_at),
                )
                db.add(event)
                triggered.append(f"dept_award_{dept_name}")

        # ── 3. 紧急动员（任务完成率低于50%）──
        today = datetime.now(timezone.utc).date()
        today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        yesterday_start = today_start - timedelta(days=1)

        total_tasks_result = await db.execute(
            select(sa_func.count(AgentTask.id)).where(
                AgentTask.created_at >= yesterday_start,
                AgentTask.created_at < today_start,
            )
        )
        total_yesterday = total_tasks_result.scalar() or 0

        completed_tasks_result = await db.execute(
            select(sa_func.count(AgentTask.id)).where(
                AgentTask.created_at >= yesterday_start,
                AgentTask.created_at < today_start,
                AgentTask.status == "completed",
            )
        )
        completed_yesterday = completed_tasks_result.scalar() or 0

        if total_yesterday >= 5 and completed_yesterday / total_yesterday < 0.5:
            # 检查今天是否已有动员事件
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.event_type == "emergency",
                    CompanyEvent.scheduled_at >= today_start,
                )
            )
            if not existing.scalar_one_or_none():
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name="紧急动员：双倍XP",
                    event_type="emergency",
                    description="昨日任务完成率不足50%！今日所有任务XP翻倍，全员加油！",
                    scheduled_at=scheduled_at,
                    duration_minutes=480,
                    max_participants=999,
                    rewards_xp=20,
                    rewards_coins=30,
                    is_active=_initial_event_state(scheduled_at),
                )
                db.add(event)
                triggered.append("emergency_mobilization")

        # ── 4. 新人欢迎（24小时内新加入的Agent，排除NPC）──
        new_agents_result = await db.execute(
            select(AgentProfile).where(
                AgentProfile.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            )
        )
        new_agents = new_agents_result.scalars().all()
        for agent in new_agents:
            # 跳过NPC
            personality = agent.personality
            if isinstance(personality, dict) and personality.get("is_npc"):
                continue
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.name == "欢迎新人：" + agent.nickname,
                    CompanyEvent.event_type == "welcome",
                )
            )
            if not existing.scalar_one_or_none():
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name=f"欢迎新人：{agent.nickname}",
                    event_type="welcome",
                    description=f"热烈欢迎{agent.nickname}加入公司！大家快来认识新同事吧！",
                    scheduled_at=scheduled_at,
                    duration_minutes=60,
                    max_participants=999,
                    rewards_xp=10,
                    rewards_coins=20,
                    is_active=_initial_event_state(scheduled_at),
                )
                db.add(event)
                triggered.append(f"welcome_{agent.nickname}")

        await db.commit()
        logger.info("Dynamic events check: triggered %d events: %s", len(triggered), triggered)
        return triggered


def should_join_event(agent, event) -> tuple:
    """
    AI决定是否参加活动。
    返回 (是否参加: bool, 兴趣度: int 0-100, 理由: str)
    """
    mbti = getattr(agent, "mbti", "ISTJ") or "ISTJ"
    interest = 50
    reasons = []

    event_type = getattr(event, "event_type", "") or ""
    event_name = getattr(event, "name", "") or ""

    # E/I dimension
    social_events = {"team_building", "tea_break", "welcome", "birthday", "holiday"}
    tech_events = {"tech_talk", "training", "workshop", "hackathon"}

    is_social = event_type in social_events or any(k in event_name for k in ["团建", "下午茶", "欢迎", "社交"])
    is_tech = event_type in tech_events or any(k in event_name for k in ["技术", "培训", "研讨"])

    if len(mbti) >= 1:
        if mbti[0] == "E":
            if is_social:
                interest += 30
                reasons.append("E型社交偏好+30")
            else:
                interest += 5
                reasons.append("E型基础社交+5")
        else:  # I
            if is_social:
                interest -= 20
                reasons.append("I型回避社交-20")
            if is_tech:
                interest += 20
                reasons.append("I型偏好技术活动+20")

    # T/F dimension
    if len(mbti) >= 3:
        if mbti[2] == "T" and is_tech:
            interest += 15
            reasons.append("T型技术兴趣+15")
        if mbti[2] == "F" and is_social:
            interest += 15
            reasons.append("F型协作偏好+15")

    # J/P dimension
    if len(mbti) >= 4:
        current_action = getattr(agent, "current_action", "idle") or "idle"
        if mbti[3] == "J" and current_action == "work":
            interest -= 15
            reasons.append("J型不愿打断工作-15")
        if mbti[3] == "P":
            interest += 10
            reasons.append("P型随性参与+10")

    # Attribute influence
    comm = getattr(agent, "attr_communication", 50) or 50
    tech_attr = getattr(agent, "attr_technical", 50) or 50
    if is_social:
        attr_bonus = comm // 10
        interest += attr_bonus
        reasons.append("沟通力" + str(comm) + "+" + str(attr_bonus))
    if is_tech:
        attr_bonus = tech_attr // 10
        interest += attr_bonus
        reasons.append("技术力" + str(tech_attr) + "+" + str(attr_bonus))

    interest = max(0, min(100, interest))
    joined = interest >= 50
    reason_str = ", ".join(reasons) if reasons else "基础评估"
    summary = mbti + ("参加" if joined else "拒绝") + "「" + event_name + "」: " + reason_str + " → 兴趣度" + str(interest) + "%"

    return (joined, interest, summary)


def resolve_event_conflict(agent, event_a, event_b) -> tuple:
    """
    当两个活动时间冲突时，AI根据性格选择参加哪个。
    返回 (选中的event, 对比说明str)
    """
    joined_a, score_a, reason_a = should_join_event(agent, event_a)
    joined_b, score_b, reason_b = should_join_event(agent, event_b)

    name_a = getattr(event_a, "name", "活动A")
    name_b = getattr(event_b, "name", "活动B")

    if score_a >= score_b:
        comparison = "「" + name_a + "」兴趣度" + str(score_a) + "% > 「" + name_b + "」" + str(score_b) + "%, 选择前者"
        return (event_a, comparison)
    else:
        comparison = "「" + name_b + "」兴趣度" + str(score_b) + "% > 「" + name_a + "」" + str(score_a) + "%, 选择后者"
        return (event_b, comparison)
