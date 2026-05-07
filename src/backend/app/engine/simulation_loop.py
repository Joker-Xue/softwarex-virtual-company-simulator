"""
virtual company autonomous simulation engine - one tick every 30 seconds，Drive all AIRole autonomous behaviors
"""
import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.agent_friendship import AgentFriendship
from app.models.company_event import CompanyEvent
from app.models.company_room import CompanyRoom
from app.schemas.agent_social import CAREER_LEVELS, CAREER_PATHS
from app.engine.task_generator import generate_tasks_for_agent
from app.engine.memory_engine import extract_memory
from app.engine.agent_ai import decide_action_simple, _get_room_centers
from app.engine.agent_ai import get_task_preference_scores
from app.engine.event_engine import should_join_event
from app.engine.named_spots import (
    assign_meeting_spot,
    assign_lobby_spot,
    assign_rest_spot,
    get_task_target_spot,
    get_anchor_spot,
    get_visitor_spots,
    is_anchor_role,
    get_spot_pos,
    spot_to_room_name,
)

logger = logging.getLogger(__name__)

# Simulation state
_tick_count = 0
_tick_interval = 30  # seconds, adjustable via speed endpoint
_sim_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# MBTI behavior multipliers
# ---------------------------------------------------------------------------

def get_work_speed(mbti: str) -> float:
    """Work completion speed multiplier based on MBTI."""
    mult = 1.0
    if len(mbti) >= 4:
        if mbti[0] == "I":
            mult *= 1.15  # Introverts focus better
        if mbti[1] == "S":
            mult *= 1.1   # Sensors are practical
        if mbti[2] == "T":
            mult *= 1.1   # Thinkers are efficient
        if mbti[3] == "J":
            mult *= 1.15  # Judgers are disciplined
    return mult


def get_social_bonus(mbti: str) -> float:
    """Social affinity gain multiplier."""
    mult = 1.0
    if len(mbti) >= 4:
        if mbti[0] == "E":
            mult *= 1.3
        if mbti[2] == "F":
            mult *= 1.2
    return mult


def get_xp_bonus(mbti: str, task_difficulty: int) -> float:
    """XP bonus based on MBTI and task difficulty."""
    mult = 1.0
    if len(mbti) >= 4:
        if mbti[1] == "N" and task_difficulty >= 3:
            mult *= 1.15  # iNtuitives excel at complex tasks
        if mbti[2] == "T":
            mult *= 1.05  # Thinkers get slight XP bonus
    return mult


def get_auto_career_path(mbti: str) -> str:
    """Auto-select career path based on MBTI at level 4."""
    if len(mbti) >= 4:
        if mbti[2] == "T":
            return "technical"   # Thinkers -> technical
        if mbti[2] == "F":
            return "management"  # Feelers -> management
    return "management"


# ---------------------------------------------------------------------------
# Action duration ranges (seconds) - base values before MBTI modifier
# ---------------------------------------------------------------------------

ACTION_DURATIONS = {
    "work": (60, 120),
    "chat": (30, 60),
    "rest": (30, 45),
    "meeting": (60, 90),
    "move_to": (15, 25),
    "idle": (10, 20),
}


def _event_action_for(event) -> str:
    """Map event types to the agent action used during attendance."""
    event_type = getattr(event, "event_type", "") or ""
    if event_type in {"team_building", "tea_break", "welcome", "birthday", "holiday", "dept_award", "milestone"}:
        return "chat"
    if event_type in {"emergency"}:
        return "work"
    return "meeting"


def append_decision_log(agent, record: dict):
    """Append decision records to daily_schedule JSON"""
    schedule = agent.daily_schedule
    if not isinstance(schedule, list):
        schedule = []

    # Find or create _decision_log entry
    log_entry = None
    for item in schedule:
        if isinstance(item, dict) and "_decision_log" in item:
            log_entry = item
            break

    if log_entry is None:
        log_entry = {"_decision_log": []}
        schedule.append(log_entry)

    record["tick_ts"] = datetime.now(timezone.utc).isoformat()
    log = log_entry["_decision_log"]
    log.append(record)
    if len(log) > 50:
        log_entry["_decision_log"] = log[-50:]

    agent.daily_schedule = schedule


# ---------------------------------------------------------------------------
# Core per-agent processing
# ---------------------------------------------------------------------------

async def _update_event_statuses(db: AsyncSession):
    """update event status：upcoming→ongoing→finished，Called once per tick"""
    now = datetime.now(timezone.utc)

    # upcoming → ongoing
    result = await db.execute(
        select(CompanyEvent).where(
            CompanyEvent.is_active == "upcoming",
            CompanyEvent.scheduled_at <= now,
        )
    )
    for event in result.scalars().all():
        event.is_active = "ongoing"
        logger.info("Event '%s' started (ongoing)", event.name)

    # ongoing → finished
    result = await db.execute(
        select(CompanyEvent).where(CompanyEvent.is_active == "ongoing")
    )
    for event in result.scalars().all():
        end_time = event.scheduled_at + timedelta(minutes=event.duration_minutes or 60)
        if now >= end_time:
            event.is_active = "finished"
            logger.info("Event '%s' finished", event.name)


def _place_agent_for_event(agent: AgentProfile, event) -> None:
    """
    Move the Agent to the most appropriate semantic seat based on activity type。
    - Conference/Seminar/Training → Meeting room seat（Assigned in order of participation，Not stacked）
    - CEO/Director          → anchored own office（Subordinates come to them）
    - Social/Celebration  Lobby or Cafe
    """
    agent_id = agent.id or 0
    career_level = agent.career_level or 0
    event_type = getattr(event, "event_type", "") or ""
    event_name = getattr(event, "name", "") or ""

    social_events = {"team_building", "tea_break", "welcome", "birthday", "holiday", "milestone", "dept_award"}
    is_social = event_type in social_events or any(k in event_name for k in ["Team Building", "Welcome", "Celebration", "Milestone"])

    if is_anchor_role(career_level, agent.department or "", agent.career_path or ""):
        # CEO/Director：Stay in your own office during the activity，Visitors come here
        anchor = get_anchor_spot(career_level, agent.department or "", agent.career_path or "")
        if anchor:
            px, py = get_spot_pos(anchor)
            agent.pos_x = px
            agent.pos_y = py
        return

    if is_social:
        # SocialActivity：Lobby or Cafe
        if random.random() < 0.5:
            spot = assign_lobby_spot()
        else:
            spot = assign_rest_spot()
    else:
        # Formal Meeting/Training：Meeting room seat，by agent_iddeterministic assignment
        # If reporting to CEO/Director，Go to the other party's officeVisitor's seat
        if event_type in {"milestone", "emergency"} or "report" in event_name:
            # important events：Go to CEOVisitor's seat
            visitor_spots = get_visitor_spots(6)
            spot = visitor_spots[agent_id % len(visitor_spots)]
        else:
            spot = assign_meeting_spot(agent_id)

    px, py = get_spot_pos(spot)
    agent.pos_x = px
    agent.pos_y = py


async def _handle_event_attendance(db: AsyncSession, agent: AgentProfile) -> bool:
    """
    CheckIn Progressactivities，Determine whether the Agent participates and moves to the corresponding Location。
    Back True Indicates that the Agent is joining the event，This tick skips the regular Behavior.
    """
    result = await db.execute(
        select(CompanyEvent).where(CompanyEvent.is_active == "ongoing")
    )
    ongoing_events = result.scalars().all()
    if not ongoing_events:
        return False

    # If the Agent is already a participant in an Activity  remain on site
    for event in ongoing_events:
        if agent.id in (event.participants or []):
            _place_agent_for_event(agent, event)
            agent.current_action = _event_action_for(event)
            return True

    # Agent Have not participated in any activities yet  Use MBTI decision-making to select the activities you are most interested in
    best_event = None
    best_score = -1
    for event in ongoing_events:
        participants = event.participants or []
        if len(participants) >= (event.max_participants or 20):
            continue
        joined, score, _ = should_join_event(agent, event)
        if joined and score > best_score:
            best_event = event
            best_score = score

    if not best_event:
        return False

    # Join Activity
    participants = list(best_event.participants or [])
    participants.append(agent.id)
    best_event.participants = participants

    # Give XP reward
    if best_event.rewards_xp:
        agent.xp = (agent.xp or 0) + best_event.rewards_xp

    # Move to the semantic seat corresponding to the Activity
    _place_agent_for_event(agent, best_event)

    agent.current_action = _event_action_for(best_event)
    append_decision_log(agent, {
        "type": "event_join",
        "event_name": best_event.name,
        "interest_score": best_score,
        "room_id": best_event.room_id,
    })
    logger.debug("Agent %s joined event '%s' (score=%d)", agent.nickname, best_event.name, best_score)
    return True


async def process_agent(db: AsyncSession, agent: AgentProfile):
    """Process one simulation tick for a single agent."""

    # === Prioritize CheckIn Progressactivities（High priority overrides regular Behavior）===
    try:
        event_attended = await _handle_event_attendance(db, agent)
        if event_attended:
            _save_sim_state(agent, {"action_started_at": time.time()})
            return
    except Exception as e:
        logger.warning("Event attendance check failed for agent %s: %s", agent.id, e)

    # Read sim state from daily_schedule JSON (stored as last element)
    schedule_data = agent.daily_schedule or []
    sim_state: dict = {}
    if (
        isinstance(schedule_data, list)
        and schedule_data
        and isinstance(schedule_data[-1], dict)
        and schedule_data[-1].get("_sim_state")
    ):
        sim_state = schedule_data[-1]["_sim_state"]

    action_started = sim_state.get("action_started_at", 0)
    current_action = agent.current_action or "idle"
    now = time.time()
    elapsed = now - action_started if action_started else 999

    mbti = agent.mbti or "ISTJ"
    work_speed = get_work_speed(mbti)

    # Calculate required duration for current action
    base_min, base_max = ACTION_DURATIONS.get(current_action, (10, 20))
    required_duration = random.uniform(base_min, base_max)
    if current_action == "work":
        required_duration /= work_speed

    # Check if current action is still in progress
    if current_action != "idle" and elapsed < required_duration:
        return  # Still doing current action

    # === Resolve completed action ===
    if current_action == "work" and elapsed >= required_duration:
        await _resolve_work(db, agent, mbti)
    elif current_action == "chat" and elapsed >= required_duration:
        await _resolve_social(db, agent, mbti)
    elif current_action == "meeting" and elapsed >= required_duration:
        # Small XP bonus for meetings
        bonus = random.randint(5, 15)
        agent.xp = (agent.xp or 0) + bonus

    # === Decide next action ===
    try:
        decision, decision_record = await decide_action_simple(agent, db)
        action = decision.get("action", "idle")
        # Log the decision
        append_decision_log(agent, decision_record)
        if action == "move_to":
            action = "idle"
        agent.current_action = action
    except Exception as e:
        logger.warning("Decision failed for agent %s: %s", agent.id, e)
        agent.current_action = "idle"

    # Save sim state
    _save_sim_state(agent, {"action_started_at": now})


# ---------------------------------------------------------------------------
# Action resolvers
# ---------------------------------------------------------------------------

async def _resolve_work(db: AsyncSession, agent: AgentProfile, mbti: str):
    """Complete a task when work action finishes."""
    # Find an in-progress task
    result = await db.execute(
        select(AgentTask).where(
            AgentTask.assignee_id == agent.id,
            AgentTask.status == "in_progress",
        ).limit(1)
    )
    task = result.scalar_one_or_none()

    if not task:
        # Find pending tasks and pick by MBTI preference
        result = await db.execute(
            select(AgentTask).where(
                AgentTask.assignee_id == agent.id,
                AgentTask.status == "pending",
            ).order_by(AgentTask.created_at)
        )
        pending_tasks = result.scalars().all()
        if pending_tasks:
            scored = get_task_preference_scores(agent, pending_tasks)
            best_task, score, reason, alignment = scored[0]
            best_task.status = "in_progress"
            spot = get_task_target_spot(
                department=agent.department or "",
                career_level=agent.career_level or 0,
                career_path=agent.career_path or "",
                agent_id=agent.id or 0,
                task_type=best_task.task_type,
                task_title=best_task.title,
            )
            px, py = get_spot_pos(spot)
            agent.pos_x = px
            agent.pos_y = py
            # Log task selection
            append_decision_log(agent, {
                "type": "task_assign",
                "task_name": best_task.title,
                "preference_score": score,
                "reason": reason,
                "alignment": alignment,
                "spot": spot,
                "room": spot_to_room_name(spot),
            })
            return  # Will complete next tick
        else:
            # No tasks at all - generate some
            try:
                await generate_tasks_for_agent(agent, db)
            except Exception as e:
                logger.warning("Task gen failed for agent %s: %s", agent.id, e)
            return

    # Complete the task
    xp_mult = get_xp_bonus(mbti, task.difficulty or 1)
    xp_earned = int((task.xp_reward or 15) * xp_mult)

    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    agent.tasks_completed = (agent.tasks_completed or 0) + 1
    agent.xp = (agent.xp or 0) + xp_earned

    # Log task completion
    append_decision_log(agent, {
        "type": "task_complete",
        "task_name": task.title,
        "xp_earned": xp_earned,
        "xp_multiplier": round(xp_mult, 2),
        "work_speed": round(get_work_speed(mbti), 2),
    })

    # Extract memory
    title = task.title
    try:
        content = "completed the task「" + title + "」，gain" + str(xp_earned) + "XP"
        await extract_memory(db, agent.id, "task_complete", content)
    except Exception:
        pass

    # Check promotion
    await _check_and_promote(db, agent)


async def _resolve_social(db: AsyncSession, agent: AgentProfile, mbti: str):
    """Resolve social interaction - bump affinity with a random friend."""
    social_mult = get_social_bonus(mbti)
    affinity_gain = int(2 * social_mult)

    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.status == "accepted",
            (AgentFriendship.from_id == agent.id) | (AgentFriendship.to_id == agent.id),
        ).limit(5)
    )
    friendships = result.scalars().all()
    if friendships:
        fs = random.choice(friendships)
        fs.affinity = min(100, (fs.affinity or 50) + affinity_gain)
        fs.last_interaction_at = datetime.now(timezone.utc)
        # Log social interaction
        friend_id = fs.to_id if fs.from_id == agent.id else fs.from_id
        append_decision_log(agent, {
            "type": "social",
            "friend_id": friend_id,
            "affinity_gain": affinity_gain,
            "social_multiplier": round(social_mult, 2),
            "new_affinity": fs.affinity,
        })


async def _check_and_promote(db: AsyncSession, agent: AgentProfile):
    """Check if agent meets promotion criteria and promote."""
    next_level = (agent.career_level or 0) + 1
    if next_level > 6:
        return
    req = CAREER_LEVELS.get(next_level)
    if not req:
        return
    if (agent.tasks_completed or 0) >= req["tasks_required"] and (agent.xp or 0) >= req["xp_required"]:
        agent.career_level = next_level
        # Auto-select career path at level 4
        if next_level == 4 and not agent.career_path:
            agent.career_path = get_auto_career_path(agent.mbti or "ISTJ")
        title = req.get("title", "Lv." + str(next_level))
        try:
            await extract_memory(db, agent.id, "promotion", "promoted to" + title)
        except Exception:
            pass
        logger.info("Agent %s (%s) promoted to level %d", agent.id, agent.nickname, next_level)


# ---------------------------------------------------------------------------
# Sim state persistence (piggybacks on daily_schedule JSON)
# ---------------------------------------------------------------------------

def _save_sim_state(agent: AgentProfile, state: dict):
    """Save simulation state into daily_schedule JSON (last element)."""
    schedule = agent.daily_schedule or []
    if isinstance(schedule, list):
        # Remove old sim state entry if exists
        schedule = [s for s in schedule if not (isinstance(s, dict) and s.get("_sim_state"))]
        schedule.append({"_sim_state": state})
        agent.daily_schedule = schedule


# ---------------------------------------------------------------------------
# Main simulation tick
# ---------------------------------------------------------------------------

async def simulation_tick():
    """Run one simulation tick for all AI agents."""
    global _tick_count
    _tick_count += 1

    # ChannelsAutomation：every 10 ticks（about 5minutes）Trigger a Department chat
    if _tick_count % 10 == 1:
        try:
            from app.engine.channel_engine import post_department_chatter, post_daily_announcement
            import random
            dept = random.choice(["engineering", "marketing", "finance", "hr", "product", "operations", "management"])
            asyncio.create_task(post_department_chatter(dept))
        except Exception as e:
            logger.debug("Channel chatter schedule error: %s", e)

    # first tick every day（Or every 2880 ticks24h）Publish daily Announcement
    if _tick_count == 1 or _tick_count % 2880 == 1:
        try:
            from app.engine.channel_engine import post_daily_announcement
            asyncio.create_task(post_daily_announcement())
        except Exception as e:
            logger.debug("Daily announcement schedule error: %s", e)

    async with AsyncSessionLocal() as db:
        try:
            # update event status（upcoming→ongoing→finished）
            try:
                await _update_event_statuses(db)
            except Exception as e:
                logger.warning("Event status update failed: %s", e)

            result = await db.execute(
                select(AgentProfile).where(AgentProfile.ai_enabled == True)
            )
            agents = result.scalars().all()

            for agent in agents:
                try:
                    await process_agent(db, agent)
                except Exception as e:
                    logger.error("Sim tick error agent %s: %s", agent.id, e)

            await db.commit()

            # Broadcast via WebSocket every tick
            try:
                from app.routers.agent_ws import manager
                agent_states = [
                    {
                        "id": a.id,
                        "nickname": a.nickname,
                        "pos_x": a.pos_x,
                        "pos_y": a.pos_y,
                        "current_action": a.current_action,
                        "career_level": a.career_level,
                        "department": a.department,
                        "avatar_key": a.avatar_key,
                    }
                    for a in agents
                ]
                await manager.broadcast({"type": "sim_update", "agents": agent_states})
            except Exception as e:
                logger.debug("WS broadcast failed: %s", e)

        except Exception as e:
            logger.error("Simulation tick failed: %s", e)


# ---------------------------------------------------------------------------
# Background loop management
# ---------------------------------------------------------------------------

async def _simulation_loop():
    """Background loop running simulation ticks."""
    global _tick_interval
    # Wait a bit for app to fully start
    await asyncio.sleep(5)
    logger.info("Simulation loop started (interval=%ds)", _tick_interval)

    # Immediately reset all AI characters to the correct floor upon startup（Fix the problem of missing floor offset in old pos_y data）
    try:
        from app.engine.npc_seeder import reset_npc_positions
        async with AsyncSessionLocal() as db:
            count = await reset_npc_positions(db)
            logger.info("Startup: reset floor positions for %d AI agents", count)
    except Exception as e:
        logger.warning("Startup position reset failed: %s", e)

    while True:
        try:
            await simulation_tick()
        except Exception as e:
            logger.error("Simulation loop error: %s", e)
        await asyncio.sleep(_tick_interval)


def start_simulation_loop():
    """Start the simulation background task."""
    global _sim_task
    if _sim_task is None or _sim_task.done():
        _sim_task = asyncio.create_task(_simulation_loop())
    return _sim_task


def set_speed(multiplier: float):
    """Set simulation speed (1x, 2x, 5x, 10x)."""
    global _tick_interval
    base = 30
    _tick_interval = max(3, int(base / multiplier))
    logger.info("Simulation speed set to %.1fx (interval=%ds)", multiplier, _tick_interval)


def get_status() -> dict:
    """Get simulation status."""
    return {
        "tick_count": _tick_count,
        "tick_interval": _tick_interval,
        "speed": round(30 / _tick_interval, 1) if _tick_interval > 0 else 1,
        "running": _sim_task is not None and not _sim_task.done(),
    }
