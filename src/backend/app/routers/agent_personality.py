"""
personalitytraceAPI - Demonstrating the transparent impact of MBTI on AI decision-making
"""
import re
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.engine.simulation_loop import get_work_speed, get_social_bonus, get_xp_bonus, get_auto_career_path
from app.engine.agent_ai import _get_mbti_weights, get_task_preference_scores

router = APIRouter()


def _parse_task_meta(description: str) -> dict:
    """parse task descriptionLocation and Contact metadata in。
    Format：[Location:XXX|Contact:XXX] original description
    """
    if not description:
        return {"location": "", "contact": ""}
    m = re.match(r'^\[Location:([^|]+)\|Contact:([^\]]+)\]', description)
    if m:
        return {"location": m.group(1).strip(), "contact": m.group(2).strip()}
    return {"location": "", "contact": ""}


@router.get("/personality-trace", summary="Get Personality Trace")
async def get_personality_trace(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentProfile).where(AgentProfile.user_id == user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Profile has not been created yet")

    mbti = agent.mbti or "ISTJ"

    # Effective multipliers
    multipliers = {
        "work_speed": round(get_work_speed(mbti), 2),
        "social_bonus": round(get_social_bonus(mbti), 2),
        "xp_bonus": round(get_xp_bonus(mbti, 3), 2),
        "career_tendency": get_auto_career_path(mbti),
    }

    # Action weights (personality tendency)
    weights = _get_mbti_weights(mbti)
    total = sum(weights.values())
    probabilities = {k: round(v / total * 100, 1) for k, v in weights.items()}

    # Preferred task tags
    tag_prefs = []
    if mbti[2] == "T":
        tag_prefs = ["technical", "coding", "architecture"]
    else:
        tag_prefs = ["social", "mentoring", "team"]
    if mbti[1] == "N":
        tag_prefs += ["creative", "innovation"]
    else:
        tag_prefs += ["management", "routine"]

    # Decision log from daily_schedule
    decisions = []
    schedule = agent.daily_schedule or []
    for item in schedule:
        if isinstance(item, dict) and "_decision_log" in item:
            decisions = item["_decision_log"]
            break

    # Event join rate
    event_decisions = [d for d in decisions if d.get("type") == "event"]
    event_joins = sum(1 for d in event_decisions if d.get("joined"))
    event_rate = round(event_joins / len(event_decisions), 2) if event_decisions else 0.5

    # Sort action weights for most/least likely
    sorted_actions = sorted(probabilities.items(), key=lambda x: -x[1])
    action_labels = {"work": "Work", "chat": "Social", "rest": "Rest", "move_to": "walk around", "meeting": "Meeting"}

    return {
        "mbti": mbti,
        "effective_multipliers": multipliers,
        "personality_tendency": {
            "action_weights": weights,
            "action_probabilities": probabilities,
            "most_likely_action": action_labels.get(sorted_actions[0][0], sorted_actions[0][0]) + " (" + str(sorted_actions[0][1]) + "%)",
            "least_likely_action": action_labels.get(sorted_actions[-1][0], sorted_actions[-1][0]) + " (" + str(sorted_actions[-1][1]) + "%)",
            "preferred_task_tags": tag_prefs[:4],
            "event_join_rate": event_rate,
        },
        "recent_decisions": decisions[-30:],
    }


@router.get("/task-status", summary="Get Current Task Status")
async def get_task_status(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentProfile).where(AgentProfile.user_id == user.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Profile has not been created yet")

    mbti = agent.mbti or "ISTJ"
    work_speed = get_work_speed(mbti)

    # Current in-progress task
    ip_result = await db.execute(
        select(AgentTask).where(
            AgentTask.assignee_id == agent.id,
            AgentTask.status == "in_progress",
        ).limit(1)
    )
    current_task_obj = ip_result.scalar_one_or_none()

    current_task = None
    if current_task_obj:
        diff = current_task_obj.difficulty or 1
        base_time = diff * 90
        # Check tag affinity
        task_tag = current_task_obj.task_type or ""
        tag_affinity = 1.0
        if mbti[2] == "T" and any(k in task_tag.lower() for k in ["technical", "project", "coding"]):
            tag_affinity = 1.2
        elif mbti[2] == "F" and any(k in task_tag.lower() for k in ["social", "team"]):
            tag_affinity = 1.2
        elif mbti[1] == "N" and any(k in task_tag.lower() for k in ["creative", "innovation"]):
            tag_affinity = 1.2
        elif mbti[1] == "S" and any(k in task_tag.lower() for k in ["management", "routine"]):
            tag_affinity = 1.2

        estimated = base_time / work_speed / tag_affinity

        # Estimate progress from sim state
        sim_started = 0
        schedule = agent.daily_schedule or []
        for item in schedule:
            if isinstance(item, dict) and item.get("_sim_state"):
                sim_started = item["_sim_state"].get("action_started_at", 0)

        elapsed = time.time() - sim_started if sim_started else 0
        progress = min(elapsed / estimated * 100, 99.9) if estimated > 0 else 0

        # Find selection reason from decision log
        selection_reason = ""
        for item in schedule:
            if isinstance(item, dict) and "_decision_log" in item:
                for log in reversed(item["_decision_log"]):
                    if log.get("type") == "task_assign" and log.get("task_name") == current_task_obj.title:
                        selection_reason = log.get("reason", "")
                        break
                break

        tag_affinity_str = str(round(tag_affinity, 1)) + "x"
        if tag_affinity > 1.0:
            tag_affinity_str += "(tag match)"

        meta = _parse_task_meta(current_task_obj.description or "")
        current_task = {
            "task_id": current_task_obj.id,
            "name": current_task_obj.title,
            "difficulty": diff,
            "task_type": task_tag,
            "progress_pct": round(progress, 1),
            "estimated_duration_s": round(estimated),
            "elapsed_s": round(elapsed),
            "selection_reason": selection_reason,
            "location": meta["location"],
            "contact_person": meta["contact"],
            "speed_factors": {
                "base_time": str(base_time) + "s",
                "work_speed": str(round(work_speed, 2)) + "x",
                "tag_affinity": tag_affinity_str,
                "final_duration": str(round(estimated)) + "s",
            },
        }

    # Task queue (pending tasks sorted by preference)
    pending_result = await db.execute(
        select(AgentTask).where(
            AgentTask.assignee_id == agent.id,
            AgentTask.status == "pending",
        ).order_by(AgentTask.created_at)
    )
    pending_tasks = pending_result.scalars().all()

    task_queue = []
    if pending_tasks:
        scored = get_task_preference_scores(agent, pending_tasks)
        for task_obj, score, reason, alignment in scored[:3]:
            meta = _parse_task_meta(task_obj.description or "")
            task_queue.append({
                "task_id": task_obj.id,
                "name": task_obj.title,
                "difficulty": task_obj.difficulty or 1,
                "task_type": task_obj.task_type or "",
                "preference_score": score,
                "mbti_alignment": alignment,
                "reason": reason,
                "location": meta["location"],
                "contact_person": meta["contact"],
            })

    return {
        "current_task": current_task,
        "task_queue": task_queue,
    }
