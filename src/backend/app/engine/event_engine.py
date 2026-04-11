"""
Dynamic event engine - automatically trigger events based on company metrics
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

# MilestoneXP threshold
XP_MILESTONES = [1000, 5000, 10000, 25000, 50000, 100000]


def _initial_event_state(scheduled_at: datetime, now: datetime | None = None) -> str:
    """Only allow upcoming/ongoing/finished event states."""
    now = now or datetime.now(timezone.utc)
    return "ongoing" if scheduled_at <= now else "upcoming"


async def check_dynamic_events():
    """Check and trigger dynamic events once per hour."""
    async with AsyncSessionLocal() as db:
        triggered = []

        # ── 1. Company GeneralXPMilestone ──
        total_xp_result = await db.execute(
            select(sa_func.sum(AgentProfile.xp))
        )
        total_xp = total_xp_result.scalar() or 0

        for milestone in XP_MILESTONES:
            if total_xp >= milestone:
                # Check whether the Milestone event has been triggered
                existing = await db.execute(
                    select(CompanyEvent).where(
                        CompanyEvent.name == f"Company Milestone: {milestone} XP",
                        CompanyEvent.event_type == "milestone",
                    )
                )
                if not existing.scalar_one_or_none():
                    scheduled_at = datetime.now(timezone.utc)
                    event = CompanyEvent(
                        name=f"Company Milestone: {milestone} XP",
                        event_type="milestone",
                        description=f"Company XP exceeded {milestone}. Celebrate together and earn bonus rewards.",
                        scheduled_at=scheduled_at,
                        duration_minutes=120,
                        max_participants=999,
                        rewards_xp=50,
                        rewards_coins=100,
                        is_active=_initial_event_state(scheduled_at),
                    )
                    db.add(event)
                    triggered.append(f"milestone_{milestone}")

        # ── 2. Outstanding Department Commendation（top output this week）──
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
            # Only triggers once a week
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.event_type == "dept_award",
                    CompanyEvent.scheduled_at >= week_ago,
                )
            )
            if not existing.scalar_one_or_none():
                dept_labels = {
                    "engineering": "Engineering",
                    "marketing": "Marketing",
                    "finance": "Finance",
                    "hr": "HR Department",
                }
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name=f"Outstanding Department: {dept_labels.get(dept_name, dept_name)}",
                    event_type="dept_award",
                    description=f"{dept_labels.get(dept_name, dept_name)} delivered the highest output this week ({top_dept_row.task_count} tasks). Recognition to the whole team.",
                    scheduled_at=scheduled_at,
                    duration_minutes=60,
                    max_participants=999,
                    rewards_xp=30,
                    rewards_coins=50,
                    is_active=_initial_event_state(scheduled_at),
                )
                db.add(event)
                triggered.append(f"dept_award_{dept_name}")

        # ── 3. Emergency Mobilization（Task Completion rate is less than 50%）──
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
            # Check if there are any mobilization events today
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.event_type == "emergency",
                    CompanyEvent.scheduled_at >= today_start,
                )
            )
            if not existing.scalar_one_or_none():
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name="Emergency Mobilization: Double XP",
                    event_type="emergency",
                    description="Yesterday's task completion rate fell below 50%. All task XP is doubled today to help the team recover.",
                    scheduled_at=scheduled_at,
                    duration_minutes=480,
                    max_participants=999,
                    rewards_xp=20,
                    rewards_coins=30,
                    is_active=_initial_event_state(scheduled_at),
                )
                db.add(event)
                triggered.append("emergency_mobilization")

        # ── 4. Welcome（New Agent added within 24 hours，Exclude NPCs）──
        new_agents_result = await db.execute(
            select(AgentProfile).where(
                AgentProfile.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            )
        )
        new_agents = new_agents_result.scalars().all()
        for agent in new_agents:
            # Skip NPC
            personality = agent.personality
            if isinstance(personality, dict) and personality.get("is_npc"):
                continue
            existing = await db.execute(
                select(CompanyEvent).where(
                    CompanyEvent.name == "Welcome aboard: " + agent.nickname,
                    CompanyEvent.event_type == "welcome",
                )
            )
            if not existing.scalar_one_or_none():
                scheduled_at = datetime.now(timezone.utc)
                event = CompanyEvent(
                    name=f"Welcome aboard: {agent.nickname}",
                    event_type="welcome",
                    description=f"Please welcome {agent.nickname} to the company and say hello to the new teammate.",
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
    """Decide whether an agent should join an event.
    Returns (joined: bool, preference score: int 0-100, reason: str).
    """
    mbti = getattr(agent, "mbti", "ISTJ") or "ISTJ"
    interest = 50
    reasons = []

    event_type = getattr(event, "event_type", "") or ""
    event_name = getattr(event, "name", "") or ""

    # E/I dimension
    social_events = {"team_building", "tea_break", "welcome", "birthday", "holiday"}
    tech_events = {"tech_talk", "training", "workshop", "hackathon"}

    is_social = event_type in social_events or any(k in event_name for k in ["Team Building", "Afternoon Tea", "Welcome", "Social"])
    is_tech = event_type in tech_events or any(k in event_name for k in ["technology", "Training", "discuss"])

    if len(mbti) >= 1:
        if mbti[0] == "E":
            if is_social:
                interest += 30
                reasons.append("Type E social preference +30")
            else:
                interest += 5
                reasons.append("Type E baseline social preference +5")
        else:  # I
            if is_social:
                interest -= 20
                reasons.append("Type I social avoidance -20")
            if is_tech:
                interest += 20
                reasons.append("Type I preference for technical events +20")

    # T/F dimension
    if len(mbti) >= 3:
        if mbti[2] == "T" and is_tech:
            interest += 15
            reasons.append("Type T technical interest +15")
        if mbti[2] == "F" and is_social:
            interest += 15
            reasons.append("Type F collaboration preference +15")

    # J/P dimension
    if len(mbti) >= 4:
        current_action = getattr(agent, "current_action", "idle") or "idle"
        if mbti[3] == "J" and current_action == "work":
            interest -= 15
            reasons.append("Type J avoids interrupting work -15")
        if mbti[3] == "P":
            interest += 10
            reasons.append("Type P spontaneous participation +10")

    # Attribute influence
    comm = getattr(agent, "attr_communication", 50) or 50
    tech_attr = getattr(agent, "attr_technical", 50) or 50
    if is_social:
        attr_bonus = comm // 10
        interest += attr_bonus
        reasons.append("Communication" + str(comm) + "+" + str(attr_bonus))
    if is_tech:
        attr_bonus = tech_attr // 10
        interest += attr_bonus
        reasons.append("Technical Skill" + str(tech_attr) + "+" + str(attr_bonus))

    interest = max(0, min(100, interest))
    joined = interest >= 50
    reason_str = ", ".join(reasons) if reasons else "Base evaluation"
    summary = f'{mbti}{" joined " if joined else " skipped "}"{event_name}": {reason_str} -> preference score {interest}%'

    return (joined, interest, summary)


def resolve_event_conflict(agent, event_a, event_b) -> tuple:
    """Resolve two conflicting events and pick the preferred one.
    Returns (selected_event, comparison_text).
    """
    joined_a, score_a, reason_a = should_join_event(agent, event_a)
    joined_b, score_b, reason_b = should_join_event(agent, event_b)

    name_a = getattr(event_a, "name", "ActivityA")
    name_b = getattr(event_b, "name", "ActivityB")

    if score_a >= score_b:
        comparison = f'"{name_a}" preference score {score_a}% > "{name_b}" {score_b}%, choose the former'
        return (event_a, comparison)
    else:
        comparison = f'"{name_b}" preference score {score_b}% > "{name_a}" {score_a}%, choose the latter'
        return (event_b, comparison)
