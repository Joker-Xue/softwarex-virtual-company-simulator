"""
AIengine - Generate autonomous behavior for offline agents
"""
import json
import random
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.company_room import CompanyRoom
from app.models.agent_action_log import AgentActionLog
from app.schemas.agent_social import CAREER_LEVELS
from app.prompts.agent_prompt import (
    AGENT_DECISION_PROMPT,
    AGENT_DECISION_PROMPT_V2,
    MBTI_HINTS,
)
from app.engine.memory_engine import (
    recall_memories,
    extract_memory,
    get_context_for_decision,
)
from app.engine.schedule_engine import (
    generate_daily_schedule,
    get_current_scheduled_activity,
    get_action_for_activity,
    get_room_for_activity,
)
from app.engine.named_spots import (
    assign_work_spot,
    assign_rest_spot,
    assign_lobby_spot,
    assign_meeting_spot,
    get_after_work_spot,
    get_anchor_spot,
    get_visitor_spots,
    is_anchor_role,
    get_spot_pos,
    spot_to_room_name,
)
from app.utils.llm import call_llm_json
from app.utils.cache import cache_get, cache_set, make_cache_key

logger = logging.getLogger(__name__)

# Room center coordinate Cache
_room_centers: dict = {}

# LLM DecisionCacheTTL（same agent 5minutesNo repeated requests within）
LLM_DECISION_CACHE_TTL = 300  # 5 minutes

# Floor Y coordinate offset：each floor offset 700，Avoid overlapping coordinates on different floors
# floor 1: pos_y ∈ [0, 699]，floor 2: pos_y ∈ [700, 1399]，floor 3: pos_y ∈ [1400, 2099]
FLOOR_Y_OFFSET = 700


def clear_room_cache():
    """Clear the room center coordinate Cache，Rebuild from DB on next call（Contains floor coding）。"""
    global _room_centers
    _room_centers = {}


async def _get_room_centers(db: AsyncSession) -> dict:
    """Get the center coordinates of all rooms. y coordinate encoded floor offset，Canvasy can be restored via pos_y % FLOOR_Y_OFFSET."""
    global _room_centers
    if _room_centers:
        return _room_centers
    result = await db.execute(select(CompanyRoom))
    rooms = result.scalars().all()
    for r in rooms:
        canvas_x = r.x + r.width // 2
        canvas_y = r.y + r.height // 2
        floor = r.floor or 1
        _room_centers[r.name] = {
            "x": canvas_x,
            "y": canvas_y,                                          # Original canvasy（For reference only）
            "encoded_y": canvas_y + (floor - 1) * FLOOR_Y_OFFSET,  # pos_y with floor offset
            "type": r.room_type,
            "department": r.department,
            "floor": floor,
        }
    return _room_centers


def _get_mbti_weights(mbti: str) -> dict:
    """Calculate Behavior weight based on MBTI"""
    weights = {"work": 30, "chat": 20, "rest": 15, "move_to": 25, "meeting": 10}

    if mbti[0] == "E":
        weights["chat"] += 15
        weights["move_to"] += 10
    else:
        weights["work"] += 15

    if mbti[2] == "T":
        weights["work"] += 10
    else:
        weights["chat"] += 10

    if mbti[3] == "J":
        weights["work"] += 10
    else:
        weights["move_to"] += 10
        weights["rest"] += 5

    return weights


def _weighted_choice(weights: dict) -> str:
    items = list(weights.items())
    total = sum(w for _, w in items)
    r = random.uniform(0, total)
    cumulative = 0
    for action, w in items:
        cumulative += w
        if r <= cumulative:
            return action
    return items[-1][0]


async def _ensure_daily_schedule(profile: AgentProfile, db: AsyncSession) -> list[dict]:
    """Make sure the Agent has a daily schedule，If not, generate a copy and persist it"""
    schedule = profile.daily_schedule
    if schedule:
        return schedule
    # Generate new daily schedule
    schedule = generate_daily_schedule(profile)
    profile.daily_schedule = schedule
    return schedule


def _get_current_room(profile: AgentProfile, rooms: dict) -> str:
    """Calculate the room where Current is located based on Agent coordinates"""
    px, py = profile.pos_x or 0, profile.pos_y or 0
    best_room = "Unknown area"
    best_dist = float("inf")
    for name, info in rooms.items():
        dx = px - info["x"]
        dy = py - info["y"]
        dist = dx * dx + dy * dy
        if dist < best_dist:
            best_dist = dist
            best_room = name
    return best_room


def _apply_named_spot(profile: AgentProfile, action: str) -> str:
    """
    Select semantic seats based on action and profile Info and update pos_x/pos_y.
    BackSelected seat name（for logs）。

    rules：
    - CEO/Director（anchor Role）：Work/Meeting/Idle  anchored own officeanchor point，Receiving visitors  Visitor next to anchor point's seat
    - regular staff work  → Departmentdesk
    - regular staff chat  → When visiting an executive, go to the visitor's seat in the other party's office，Otherwise go to Lobby/Cafe
    - regular staff rest  → Cafe
    - regular staff meeting → Meeting room seat
    - regular staff move_to/idle → Lobby
    """
    agent_id = profile.id or 0
    career_level = profile.career_level or 0
    career_path = profile.career_path or ""
    dept = (profile.department or "").strip()

    # ── executive：Anchor in your own office
    if is_anchor_role(career_level, dept, career_path):
        anchor = get_anchor_spot(career_level, dept, career_path)
        if anchor:
            if action == "chat":
                # Take the Visitor seat when receiving visitors's next to seat（Stay at anchor point by yourself）
                spot = anchor
            else:
                spot = anchor
            px, py = get_spot_pos(spot)
            profile.pos_x = px
            profile.pos_y = py
            return spot

    # ── regular staff ──
    if action == "work":
        spot = assign_work_spot(dept, agent_id)
        if spot is None:
            # UnknownDepartment → Lobby
            spot = "lobby_reception"
    elif action == "chat":
        # DepartmentStaffchat：30% Chances are you can go to the third floor to visit Executive，70% Go to Lobby/Cafe
        if random.random() < 0.3:
            # Director office visitor seat
            visitor_spots = get_visitor_spots(5)  # Director level
            spot = random.choice(visitor_spots)
        else:
            if random.random() < 0.5:
                spot = assign_lobby_spot()
            else:
                spot = assign_rest_spot()
    elif action == "rest":
        spot = assign_rest_spot()
    elif action == "meeting":
        spot = assign_meeting_spot(agent_id)
    else:
        # idle / move_to
        spot = assign_lobby_spot()

    px, py = get_spot_pos(spot)
    profile.pos_x = px
    profile.pos_y = py
    return spot


async def decide_action_llm(
    profile: AgentProfile,
    db: AsyncSession,
    nearby_agents: list | None = None,
) -> dict:
    """
    LLM-powered decision making using DeepSeek-V3.

    Flow:
    1. Check Redis cache (same agent within 5min -> return cached)
    2. Gather context: memories, nearby agents, pending tasks
    3. Build prompt using AGENT_DECISION_PROMPT_V2
    4. Call LLM via call_llm_json() with cache_prefix="agent_decision"
    5. Parse response {action, target, reason, dialogue}
    6. Write reason/dialogue to action_log and memory
    7. Fallback to decide_action_simple() on error
    """
    agent_id = profile.id
    cache_key = make_cache_key("agent_decision", str(agent_id))

    # ── Check RedisCache：same agent 5minutesNo repeated requests within ──
    cached_decision = await cache_get(cache_key)
    if cached_decision:
        logger.debug("Using cached LLM decision for agent %d", agent_id)
        action = cached_decision.get("action", "idle")
        _apply_named_spot(profile, action)
        profile.current_action = action if action != "move_to" else "idle"
        return cached_decision

    try:
        # ── 1. Collect contextInfo ──
        context = await get_context_for_decision(db, agent_id)
        rooms = await _get_room_centers(db)
        career_info = CAREER_LEVELS.get(profile.career_level or 0, {})
        career_title = career_info.get("title", "Intern")

        # Schedule text
        schedule = await _ensure_daily_schedule(profile, db)
        scheduled = get_current_scheduled_activity(schedule)
        if scheduled:
            schedule_context = f"Current schedule: {scheduled['time']} - {scheduled['activity']}（{scheduled['room_type']}）"
        else:
            schedule_context = "CurrentNo schedule"

        # MBTI hints
        mbti = profile.mbti or "ISTJ"
        hints = "\n".join(
            f"- {MBTI_HINTS.get(ch, '')}" for ch in mbti if ch in MBTI_HINTS
        )

        # RoomInfo
        rooms_info = "\n".join(
            f"- {name}: type={info['type']}, Department={info['department']}"
            for name, info in rooms.items()
        )

        # Nearby Agent Description
        if nearby_agents:
            nearby_text = ", ".join(
                f"{a.get('nickname', 'Unknown')}({a.get('department', '')})"
                for a in nearby_agents
            )
        else:
            nearby_text = "no one around"

        # Current room
        current_room = _get_current_room(profile, rooms)

        # ── 2. BuildPrompt ──
        prompt = AGENT_DECISION_PROMPT_V2.format(
            nickname=profile.nickname,
            mbti=mbti,
            career_title=career_title,
            career_level=profile.career_level or 0,
            department=profile.department or "unassigned",
            pos_x=profile.pos_x or 0,
            pos_y=profile.pos_y or 0,
            current_action=profile.current_action or "idle",
            attr_communication=profile.attr_communication or 50,
            attr_leadership=profile.attr_leadership or 50,
            attr_creativity=profile.attr_creativity or 50,
            attr_technical=profile.attr_technical or 50,
            attr_teamwork=profile.attr_teamwork or 50,
            attr_diligence=profile.attr_diligence or 50,
            memory_summary=context["memory_summary_text"],
            recent_memories=context["recent_memories_text"],
            current_room=current_room,
            nearby_agents=nearby_text,
            pending_tasks=context["pending_task_count"],
            schedule_context=schedule_context,
            rooms_info=rooms_info,
            mbti_hints=hints,
        )

        # ── 3. Call LLM ──
        llm_result = await call_llm_json(
            prompt,
            system_prompt="you are a virtual companyAIStaffAction Decisionengine。Please output JSON format strictly according to the requirements.。",
            cache_prefix="agent_decision",
        )

        # ── 4. Parse results ──
        if isinstance(llm_result, dict) and "error" in llm_result:
            logger.warning("LLM decision failed for agent %d: %s", agent_id, llm_result["error"])
            result, _ = await decide_action_simple(profile, db)
            return result

        action = llm_result.get("action", "idle")
        target = llm_result.get("target", "")
        reason = llm_result.get("reason", "")
        dialogue = llm_result.get("dialogue", "")

        # Verify the legality of the action
        valid_actions = {"move_to", "work", "chat", "rest", "meeting"}
        if action not in valid_actions:
            action = "idle"

        # ── 5. UpdateAgentstate（use semantic seating instead of room center） ──
        _apply_named_spot(profile, action)
        profile.current_action = action if action != "move_to" else "idle"

        # ── 6. Write Memories and logs
        try:
            event_type = "move"
            if action == "work":
                event_type = "task_complete"
            elif action == "chat":
                event_type = "chat"

            memory_content = f"{profile.nickname} {reason}"
            if dialogue:
                memory_content += f"，Said: \"{dialogue[:30]}\""
            await extract_memory(db, agent_id, event_type, memory_content)
        except Exception as e:
            logger.warning("Failed to extract memory for agent %s: %s", agent_id, e)

        log = AgentActionLog(
            agent_id=agent_id,
            action=action,
            detail={
                "target": target,
                "reason": reason,
                "dialogue": dialogue,
                "llm_powered": True,
            },
            location=target,
        )
        db.add(log)

        # ── 7. Cache decision results（5minutes） ──
        decision = {
            "action": action,
            "target": target,
            "reason": reason,
            "dialogue": dialogue,
        }
        await cache_set(cache_key, decision, ttl=LLM_DECISION_CACHE_TTL)

        return decision

    except Exception as e:
        logger.error("LLM decision error for agent %d: %s, falling back to simple", agent_id, e)
        result, _ = await decide_action_simple(profile, db)
        return result


async def decide_action_simple(profile: AgentProfile, db: AsyncSession) -> dict:
    """Simple rules decision making（LLM is not called，for MVP）"""
    rooms = await _get_room_centers(db)

    # ── Schedule engine priority
    # Check Agent schedule，If there are activities scheduled at Current time，Prioritize action according to schedule
    schedule = await _ensure_daily_schedule(profile, db)
    scheduled = get_current_scheduled_activity(schedule)

    if scheduled:
        activity = scheduled["activity"]
        action = get_action_for_activity(activity)

        if activity == "Work":
            # executiveanchoredoffice，Others go to Departmentdesk
            spot = _apply_named_spot(profile, "work")
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，focused work（{scheduled['time']}）"
        elif activity == "lunch":
            spot = _apply_named_spot(profile, "rest")
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，lunchtime（{scheduled['time']}）"
        elif activity in ("Rest", "break"):
            spot = _apply_named_spot(profile, "rest")
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，{activity}time（{scheduled['time']}）"
        elif activity == "Social":
            spot = _apply_named_spot(profile, "chat")
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，Socialtime（{scheduled['time']}）"
        elif activity == "get off work":
            spot = get_after_work_spot(
                agent_id=profile.id or 0,
                department=profile.department or "",
                career_level=profile.career_level or 0,
                career_path=profile.career_path or "",
            )
            px, py = get_spot_pos(spot)
            profile.pos_x = px
            profile.pos_y = py
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，get off Worked（{scheduled['time']}）"
        else:
            spot = _apply_named_spot(profile, "idle")
            target = spot_to_room_name(spot)
            reason = f"follow the schedule，{activity}（{scheduled['time']}）"

        profile.current_action = action

        # extract behavior memories
        try:
            event_type = "move"
            if action == "work":
                event_type = "task_complete"
            elif action == "chat":
                event_type = "chat"
            memory_content = f"{profile.nickname} {reason}，go to{target}"
            await extract_memory(db, profile.id, event_type, memory_content)
        except Exception as e:
            logger.warning("Failed to extract memory for agent %s: %s", profile.id, e)

        # record logs
        log = AgentActionLog(
            agent_id=profile.id,
            action=action,
            detail={"target": target, "reason": reason, "scheduled": True, "schedule_time": scheduled["time"]},
            location=target,
        )
        db.add(log)

        action_dict = {"action": action, "target": target, "reason": reason}
        decision_record = {
            "type": "schedule_decision",
            "activity": activity,
            "explanation": reason,
        }
        return (action_dict, decision_record)

    # ── fallback：Use weight decision when there is no schedule matching
    weights = _get_mbti_weights(profile.mbti)

    # Recall recent Memories as decision context
    try:
        recent_memories = await recall_memories(db, profile.id, limit=5)
    except Exception as e:
        logger.warning("Failed to recall memories for agent %s: %s", profile.id, e)
        recent_memories = []

    # Adjust behavior weights based on Memories
    for mem in recent_memories:
        if mem["memory_type"] == "task" and mem["importance"] >= 7:
            # Recently completed high-importance tasks，Add RestPrefers 
            weights["rest"] = weights.get("rest", 15) + 5
        elif mem["memory_type"] == "social":
            # Recently SocialMemories，Add chatPrefers 
            weights["chat"] = weights.get("chat", 20) + 5
        elif mem["memory_type"] == "career" and mem["importance"] >= 8:
            # Recent career changes（such as promotion），Increase work enthusiasm
            weights["work"] = weights.get("work", 30) + 10

    # Levellimit
    if profile.career_level < 2:
        weights.pop("meeting", None)

    # Build MBTI bonus tracking for decision record
    mbti = profile.mbti or "ISTJ"
    mbti_bonuses = {"E/I": {}, "S/N": {}, "T/F": {}, "J/P": {}}
    if len(mbti) >= 1:
        if mbti[0] == "E":
            mbti_bonuses["E/I"] = {"chat": 15, "move_to": 10}
        else:
            mbti_bonuses["E/I"] = {"work": 15}
    if len(mbti) >= 3:
        if mbti[2] == "T":
            mbti_bonuses["T/F"] = {"work": 10}
        else:
            mbti_bonuses["T/F"] = {"chat": 10}
    if len(mbti) >= 4:
        if mbti[3] == "J":
            mbti_bonuses["J/P"] = {"work": 10}
        else:
            mbti_bonuses["J/P"] = {"move_to": 10, "rest": 5}

    # Compute probabilities
    total_weight = sum(weights.values())
    probabilities = {k: round(v / total_weight * 100, 1) for k, v in weights.items()} if total_weight > 0 else {}

    action = _weighted_choice(weights)

    # Apply semantic seating and get target location name
    chosen_spot = _apply_named_spot(profile, action)
    target = spot_to_room_name(chosen_spot)

    if action == "work":
        reason = "focused work"
    elif action == "chat":
        reason = "Find someone to chat with"
    elif action == "rest":
        reason = "Rest for a moment，have a cup of coffee"
    elif action == "move_to":
        reason = "walk around"
        action = "idle"
    elif action == "meeting":
        reason = "join meeting"
    else:
        reason = "Idle"

    profile.current_action = action

    # extract behavior memories
    try:
        event_type = "move"
        if action == "work":
            event_type = "task_complete"
        elif action == "chat":
            event_type = "chat"
        memory_content = f"{profile.nickname} {reason}，go to{target}"
        await extract_memory(db, profile.id, event_type, memory_content)
    except Exception as e:
        logger.warning("Failed to extract memory for agent %s: %s", profile.id, e)

    # record logs
    log = AgentActionLog(
        agent_id=profile.id,
        action=action,
        detail={"target": target, "reason": reason},
        location=target,
    )
    db.add(log)

    action_dict = {"action": action, "target": target, "reason": reason}

    # Build Chinese explanation
    action_labels = {"work": "Work", "chat": "Social", "rest": "Rest", "move_to": "walk around", "meeting": "Meeting"}
    explanation = mbti + "personalityPrefers : choose" + action_labels.get(action, action)
    top_actions = sorted(probabilities.items(), key=lambda x: -x[1])[:3]
    explanation += " (Probability" + str(probabilities.get(action, 0)) + "%, "
    explanation += "Top three: " + ", ".join(action_labels.get(a, a) + str(p) + "%" for a, p in top_actions) + ")"

    decision_record = {
        "type": "action_decision",
        "mbti": mbti,
        "weights": dict(weights),
        "mbti_bonuses": mbti_bonuses,
        "probabilities": probabilities,
        "chosen": action,
        "explanation": explanation,
    }

    return (action_dict, decision_record)


def get_task_preference_scores(agent, tasks) -> list:
    """Sort task list based on MBTI and attributes，Back [(task, score, reason, alignment), ...]"""
    mbti = agent.mbti or "ISTJ"
    results = []

    # MBTI tag preferences
    tag_prefs = {}
    if len(mbti) >= 4:
        if mbti[1] == "S":
            tag_prefs.update({"management": 20, "routine": 15, "process": 15, "documentation": 10})
        else:  # N
            tag_prefs.update({"creative": 20, "innovation": 15, "strategy": 15, "planning": 10})
        if mbti[2] == "T":
            tag_prefs.update({"technical": 20, "coding": 15, "debugging": 15, "architecture": 10})
        else:  # F
            tag_prefs.update({"social": 20, "mentoring": 15, "team": 15, "communication": 10})

    for task in tasks:
        score = 50  # base score
        reasons = []

        task_tag = getattr(task, "task_type", "") or ""
        # Check tag match
        for tag_key, bonus in tag_prefs.items():
            if tag_key in task_tag.lower() or tag_key in (getattr(task, "title", "") or "").lower():
                score += bonus
                dim = "N" if tag_key in ("creative", "innovation", "strategy", "planning") else \
                      "S" if tag_key in ("management", "routine", "process", "documentation") else \
                      "T" if tag_key in ("technical", "coding", "debugging", "architecture") else "F"
                reasons.append(dim + "Type Preference+" + str(bonus))
                break

        # Attribute bonus
        if "technical" in task_tag.lower() or "coding" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_technical", 50) or 50) // 10
            score += attr_bonus
            reasons.append("Technical Skill" + str(getattr(agent, "attr_technical", 50)) + "+" + str(attr_bonus))
        elif "social" in task_tag.lower() or "team" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_communication", 50) or 50) // 10
            score += attr_bonus
            reasons.append("Communication" + str(getattr(agent, "attr_communication", 50)) + "+" + str(attr_bonus))
        elif "creative" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_creativity", 50) or 50) // 10
            score += attr_bonus
            reasons.append("Creativity" + str(getattr(agent, "attr_creativity", 50)) + "+" + str(attr_bonus))
        elif "management" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_leadership", 50) or 50) // 10
            score += attr_bonus
            reasons.append("Leadership" + str(getattr(agent, "attr_leadership", 50)) + "+" + str(attr_bonus))

        # Difficulty preference
        diff = getattr(task, "difficulty", 1) or 1
        if mbti[1] == "N" and diff >= 3:
            score += 10
            reasons.append("NType Preference High Difficulty +10")

        alignment = "high" if score >= 70 else "low" if score < 40 else "neutral"
        reason_str = ", ".join(reasons) if reasons else "Base match"
        results.append((task, score, reason_str, alignment))

    results.sort(key=lambda x: -x[1])
    return results


async def _get_nearby_agents(db: AsyncSession, profile: AgentProfile, radius: int = 100) -> list[dict]:
    """Get other AgentInfo near the Agent"""
    px, py = profile.pos_x or 0, profile.pos_y or 0
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.id != profile.id,
            AgentProfile.pos_x.between(px - radius, px + radius),
            AgentProfile.pos_y.between(py - radius, py + radius),
        ).limit(5)
    )
    nearby = result.scalars().all()
    return [
        {
            "id": a.id,
            "nickname": a.nickname,
            "mbti": a.mbti,
            "department": a.department or "",
            "career_level": a.career_level or 0,
            "current_action": a.current_action or "idle",
        }
        for a in nearby
    ]


async def run_ai_tick():
    """Execute an AI decision loop��All AIRoles，Includes online and offline）"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(
                AgentProfile.ai_enabled == True,
            )
        )
        agents = result.scalars().all()

        for agent in agents:
            try:
                # Get nearby AgentInfo
                nearby = await _get_nearby_agents(db, agent)
                # Prioritize tryLLM decisions，Automatic fallback to simple decision-making on failure
                await decide_action_llm(agent, db, nearby_agents=nearby)
            except Exception as e:
                logger.error("AI tick error for agent %s: %s", agent.id, e)
                try:
                    result, _ = await decide_action_simple(agent, db)
                except Exception as e2:
                    logger.error("Simple fallback also failed for agent %s: %s", agent.id, e2)

        await db.commit()

    logger.info("AI tick completed for %d agents", len(agents))
