"""
AI决策引擎 - 为离线Agent生成自主行为
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

# 房间中心坐标缓存
_room_centers: dict = {}

# LLM决策缓存TTL（同一Agent 5分钟内不重复请求）
LLM_DECISION_CACHE_TTL = 300  # 5 minutes

# 楼层Y坐标偏移量：每层偏移700，避免不同楼层坐标重叠
# floor 1: pos_y ∈ [0, 699]，floor 2: pos_y ∈ [700, 1399]，floor 3: pos_y ∈ [1400, 2099]
FLOOR_Y_OFFSET = 700


def clear_room_cache():
    """清除房间中心坐标缓存，下次调用时从DB重新构建（含floor编码）。"""
    global _room_centers
    _room_centers = {}


async def _get_room_centers(db: AsyncSession) -> dict:
    """获取所有房间中心坐标。y坐标已编码楼层偏移，可通过 pos_y % FLOOR_Y_OFFSET 还原画布y。"""
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
            "y": canvas_y,                                          # 原始画布y（仅供参考）
            "encoded_y": canvas_y + (floor - 1) * FLOOR_Y_OFFSET,  # pos_y with floor offset
            "type": r.room_type,
            "department": r.department,
            "floor": floor,
        }
    return _room_centers


def _get_mbti_weights(mbti: str) -> dict:
    """根据MBTI计算行为权重"""
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
    """确保Agent拥有每日日程，如果没有则生成一份并持久化"""
    schedule = profile.daily_schedule
    if schedule:
        return schedule
    # 生成新的每日日程
    schedule = generate_daily_schedule(profile)
    profile.daily_schedule = schedule
    return schedule


def _get_current_room(profile: AgentProfile, rooms: dict) -> str:
    """根据Agent坐标推算当前所在房间"""
    px, py = profile.pos_x or 0, profile.pos_y or 0
    best_room = "未知区域"
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
    根据 action 和 profile 信息选择语义座位并更新 pos_x / pos_y。
    返回选中的座位名（用于日志）。

    规则：
    - CEO/总监（anchor 角色）：工作/会议/闲置 → 常驻自己办公室锚点，接待来访 → 锚点旁访客席
    - 普通员工 work  → 部门工位
    - 普通员工 chat  → 拜访高管时去对方办公室访客席，否则去大厅/咖啡厅
    - 普通员工 rest  → 咖啡厅
    - 普通员工 meeting → 会议室座椅
    - 普通员工 move_to/idle → 大厅
    """
    agent_id = profile.id or 0
    career_level = profile.career_level or 0
    career_path = profile.career_path or ""
    dept = (profile.department or "").strip()

    # ── 高管：锚定在自己办公室 ──
    if is_anchor_role(career_level, dept, career_path):
        anchor = get_anchor_spot(career_level, dept, career_path)
        if anchor:
            if action == "chat":
                # 接待来访时坐访客席旁边（自己留在锚点）
                spot = anchor
            else:
                spot = anchor
            px, py = get_spot_pos(spot)
            profile.pos_x = px
            profile.pos_y = py
            return spot

    # ── 普通员工 ──
    if action == "work":
        spot = assign_work_spot(dept, agent_id)
        if spot is None:
            # 未知部门 → 大厅
            spot = "lobby_reception"
    elif action == "chat":
        # 部门员工聊天：30% 概率上三楼拜访高管，70% 去大厅/咖啡厅
        if random.random() < 0.3:
            # 去总监办公室访客席
            visitor_spots = get_visitor_spots(5)  # 总监级别
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

    # ── 检查Redis缓存：同一Agent 5分钟内不重复请求 ──
    cached_decision = await cache_get(cache_key)
    if cached_decision:
        logger.debug("Using cached LLM decision for agent %d", agent_id)
        action = cached_decision.get("action", "idle")
        _apply_named_spot(profile, action)
        profile.current_action = action if action != "move_to" else "idle"
        return cached_decision

    try:
        # ── 1. 收集上下文信息 ──
        context = await get_context_for_decision(db, agent_id)
        rooms = await _get_room_centers(db)
        career_info = CAREER_LEVELS.get(profile.career_level or 0, {})
        career_title = career_info.get("title", "实习生")

        # 日程上下文
        schedule = await _ensure_daily_schedule(profile, db)
        scheduled = get_current_scheduled_activity(schedule)
        if scheduled:
            schedule_context = f"当前日程: {scheduled['time']} - {scheduled['activity']}（{scheduled['room_type']}）"
        else:
            schedule_context = "当前无日程安排"

        # MBTI hints
        mbti = profile.mbti or "ISTJ"
        hints = "\n".join(
            f"- {MBTI_HINTS.get(ch, '')}" for ch in mbti if ch in MBTI_HINTS
        )

        # 房间信息
        rooms_info = "\n".join(
            f"- {name}: 类型={info['type']}, 部门={info['department']}"
            for name, info in rooms.items()
        )

        # 附近Agent描述
        if nearby_agents:
            nearby_text = ", ".join(
                f"{a.get('nickname', '未知')}({a.get('department', '')})"
                for a in nearby_agents
            )
        else:
            nearby_text = "周围没有人"

        # 当前房间
        current_room = _get_current_room(profile, rooms)

        # ── 2. 构建Prompt ──
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

        # ── 3. 调用LLM ──
        llm_result = await call_llm_json(
            prompt,
            system_prompt="你是一个虚拟公司AI员工行为决策引擎。请严格按照要求输出JSON格式。",
            cache_prefix="agent_decision",
        )

        # ── 4. 解析结果 ──
        if isinstance(llm_result, dict) and "error" in llm_result:
            logger.warning("LLM decision failed for agent %d: %s", agent_id, llm_result["error"])
            result, _ = await decide_action_simple(profile, db)
            return result

        action = llm_result.get("action", "idle")
        target = llm_result.get("target", "")
        reason = llm_result.get("reason", "")
        dialogue = llm_result.get("dialogue", "")

        # 验证action合法性
        valid_actions = {"move_to", "work", "chat", "rest", "meeting"}
        if action not in valid_actions:
            action = "idle"

        # ── 5. 更新Agent状态（使用语义座位而非房间中心） ──
        _apply_named_spot(profile, action)
        profile.current_action = action if action != "move_to" else "idle"

        # ── 6. 写入记忆和日志 ──
        try:
            event_type = "move"
            if action == "work":
                event_type = "task_complete"
            elif action == "chat":
                event_type = "chat"

            memory_content = f"{profile.nickname} {reason}"
            if dialogue:
                memory_content += f"，说了: \"{dialogue[:30]}\""
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

        # ── 7. 缓存决策结果（5分钟） ──
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
    """简单规则决策（不调用LLM，用于MVP）"""
    rooms = await _get_room_centers(db)

    # ── 日程引擎优先 ──
    # 检查Agent日程，如果当前时间有安排的活动，优先按日程行动
    schedule = await _ensure_daily_schedule(profile, db)
    scheduled = get_current_scheduled_activity(schedule)

    if scheduled:
        activity = scheduled["activity"]
        action = get_action_for_activity(activity)

        if activity == "工作":
            # 高管常驻办公室，其他人去部门工位
            spot = _apply_named_spot(profile, "work")
            target = spot_to_room_name(spot)
            reason = f"按日程安排，专注工作中（{scheduled['time']}）"
        elif activity == "午餐":
            spot = _apply_named_spot(profile, "rest")
            target = spot_to_room_name(spot)
            reason = f"按日程安排，午餐时间（{scheduled['time']}）"
        elif activity in ("休息", "茶歇"):
            spot = _apply_named_spot(profile, "rest")
            target = spot_to_room_name(spot)
            reason = f"按日程安排，{activity}时间（{scheduled['time']}）"
        elif activity == "社交":
            spot = _apply_named_spot(profile, "chat")
            target = spot_to_room_name(spot)
            reason = f"按日程安排，社交时间（{scheduled['time']}）"
        elif activity == "下班":
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
            reason = f"按日程安排，下班了（{scheduled['time']}）"
        else:
            spot = _apply_named_spot(profile, "idle")
            target = spot_to_room_name(spot)
            reason = f"按日程安排，{activity}（{scheduled['time']}）"

        profile.current_action = action

        # 提取行为记忆
        try:
            event_type = "move"
            if action == "work":
                event_type = "task_complete"
            elif action == "chat":
                event_type = "chat"
            memory_content = f"{profile.nickname} {reason}，前往{target}"
            await extract_memory(db, profile.id, event_type, memory_content)
        except Exception as e:
            logger.warning("Failed to extract memory for agent %s: %s", profile.id, e)

        # 记录日志
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

    # ── 回退：无日程匹配时使用权重决策 ──
    weights = _get_mbti_weights(profile.mbti)

    # 召回近期记忆作为决策上下文
    try:
        recent_memories = await recall_memories(db, profile.id, limit=5)
    except Exception as e:
        logger.warning("Failed to recall memories for agent %s: %s", profile.id, e)
        recent_memories = []

    # 根据记忆调整行为权重
    for mem in recent_memories:
        if mem["memory_type"] == "task" and mem["importance"] >= 7:
            # 最近完成了高重要度任务，增加休息倾向
            weights["rest"] = weights.get("rest", 15) + 5
        elif mem["memory_type"] == "social":
            # 最近有社交记忆，增加聊天倾向
            weights["chat"] = weights.get("chat", 20) + 5
        elif mem["memory_type"] == "career" and mem["importance"] >= 8:
            # 最近有职业变动（如晋升），增加工作积极性
            weights["work"] = weights.get("work", 30) + 10

    # 职级限制
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

    # 应用语义座位并获取目标位置名
    chosen_spot = _apply_named_spot(profile, action)
    target = spot_to_room_name(chosen_spot)

    if action == "work":
        reason = "专注工作中"
    elif action == "chat":
        reason = "找人聊聊天"
    elif action == "rest":
        reason = "休息一下，喝杯咖啡"
    elif action == "move_to":
        reason = "四处走走"
        action = "idle"
    elif action == "meeting":
        reason = "参加会议"
    else:
        reason = "空闲中"

    profile.current_action = action

    # 提取行为记忆
    try:
        event_type = "move"
        if action == "work":
            event_type = "task_complete"
        elif action == "chat":
            event_type = "chat"
        memory_content = f"{profile.nickname} {reason}，前往{target}"
        await extract_memory(db, profile.id, event_type, memory_content)
    except Exception as e:
        logger.warning("Failed to extract memory for agent %s: %s", profile.id, e)

    # 记录日志
    log = AgentActionLog(
        agent_id=profile.id,
        action=action,
        detail={"target": target, "reason": reason},
        location=target,
    )
    db.add(log)

    action_dict = {"action": action, "target": target, "reason": reason}

    # Build Chinese explanation
    action_labels = {"work": "工作", "chat": "社交", "rest": "休息", "move_to": "走动", "meeting": "会议"}
    explanation = mbti + "性格倾向: 选择" + action_labels.get(action, action)
    top_actions = sorted(probabilities.items(), key=lambda x: -x[1])[:3]
    explanation += " (概率" + str(probabilities.get(action, 0)) + "%, "
    explanation += "前三: " + ", ".join(action_labels.get(a, a) + str(p) + "%" for a, p in top_actions) + ")"

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
    """根据MBTI和属性对任务列表排序，返回 [(task, score, reason, alignment), ...]"""
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
                reasons.append(dim + "型偏好+" + str(bonus))
                break

        # Attribute bonus
        if "technical" in task_tag.lower() or "coding" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_technical", 50) or 50) // 10
            score += attr_bonus
            reasons.append("技术力" + str(getattr(agent, "attr_technical", 50)) + "+" + str(attr_bonus))
        elif "social" in task_tag.lower() or "team" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_communication", 50) or 50) // 10
            score += attr_bonus
            reasons.append("沟通力" + str(getattr(agent, "attr_communication", 50)) + "+" + str(attr_bonus))
        elif "creative" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_creativity", 50) or 50) // 10
            score += attr_bonus
            reasons.append("创造力" + str(getattr(agent, "attr_creativity", 50)) + "+" + str(attr_bonus))
        elif "management" in task_tag.lower():
            attr_bonus = (getattr(agent, "attr_leadership", 50) or 50) // 10
            score += attr_bonus
            reasons.append("领导力" + str(getattr(agent, "attr_leadership", 50)) + "+" + str(attr_bonus))

        # Difficulty preference
        diff = getattr(task, "difficulty", 1) or 1
        if mbti[1] == "N" and diff >= 3:
            score += 10
            reasons.append("N型偏好高难度+10")

        alignment = "high" if score >= 70 else "low" if score < 40 else "neutral"
        reason_str = ", ".join(reasons) if reasons else "基础匹配"
        results.append((task, score, reason_str, alignment))

    results.sort(key=lambda x: -x[1])
    return results


async def _get_nearby_agents(db: AsyncSession, profile: AgentProfile, radius: int = 100) -> list[dict]:
    """获取Agent附近的其他Agent信息"""
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
    """执行一次AI决策循环��所有AI角色，包括在线和离线）"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(
                AgentProfile.ai_enabled == True,
            )
        )
        agents = result.scalars().all()

        for agent in agents:
            try:
                # 获取附近Agent信息
                nearby = await _get_nearby_agents(db, agent)
                # 优先尝试LLM决策，失败自动回退到简单决策
                await decide_action_llm(agent, db, nearby_agents=nearby)
            except Exception as e:
                logger.error("AI tick error for agent %s: %s", agent.id, e)
                try:
                    result, _ = await decide_action_simple(agent, db)
                except Exception as e2:
                    logger.error("Simple fallback also failed for agent %s: %s", agent.id, e2)

        await db.commit()

    logger.info("AI tick completed for %d agents", len(agents))
