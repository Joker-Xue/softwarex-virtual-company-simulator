"""
聊天系统API
"""
import asyncio
import random
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func as sa_func

from app.database import get_db, AsyncSessionLocal
from app.utils.security import get_current_active_user
from app.utils.rate_limit import check_rate_limit
from app.utils.sanitize import sanitize_text, clamp_affinity
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_message import AgentMessage
from app.models.agent_friendship import AgentFriendship
from app.schemas.agent_social import MessageSend, MessageOut
from app.engine.memory_engine import extract_memory, recall_memories, get_memory_summary
from app.models.agent_memory import AgentMemory
from app.prompts.agent_prompt import NPC_CHAT_PROMPT
from app.utils.llm import call_llm_json
from app.utils.cache import cache_get, cache_set, make_cache_key

router = APIRouter()


async def _auto_private_reply(sender_id: int, ai_agent_id: int, last_message: str):
    """私聊AI自动回复背景任务 - 在独立DB会话中运行"""
    await asyncio.sleep(random.uniform(1.5, 4.0))  # 模拟思考延迟

    async with AsyncSessionLocal() as db:
        try:
            # 加载两个角色信息
            me_result = await db.execute(select(AgentProfile).where(AgentProfile.id == sender_id))
            ai_result = await db.execute(select(AgentProfile).where(AgentProfile.id == ai_agent_id))
            me = me_result.scalar_one_or_none()
            ai_agent = ai_result.scalar_one_or_none()
            if not me or not ai_agent or not ai_agent.ai_enabled:
                return

            # 获取最近对话上下文
            chat_result = await db.execute(
                select(AgentMessage)
                .where(
                    or_(
                        and_(AgentMessage.sender_id == sender_id, AgentMessage.receiver_id == ai_agent_id),
                        and_(AgentMessage.sender_id == ai_agent_id, AgentMessage.receiver_id == sender_id),
                    )
                )
                .order_by(AgentMessage.created_at.desc())
                .limit(8)
            )
            recent = list(chat_result.scalars().all())
            recent.reverse()
            history_lines = [
                f"{(me.nickname if m.sender_id == sender_id else ai_agent.nickname)}: {m.content}"
                for m in recent
            ]
            chat_history = "\n".join(history_lines[-6:]) if history_lines else "（这是第一次对话）"

            # 获取亲密度
            fr_result = await db.execute(
                select(AgentFriendship).where(
                    or_(
                        and_(AgentFriendship.from_id == sender_id, AgentFriendship.to_id == ai_agent_id),
                        and_(AgentFriendship.from_id == ai_agent_id, AgentFriendship.to_id == sender_id),
                    ),
                    AgentFriendship.status == "accepted",
                )
            )
            friendship = fr_result.scalar_one_or_none()
            affinity = friendship.affinity if friendship else 30
            affinity_label = _get_affinity_label(affinity)

            from app.schemas.agent_social import CAREER_LEVELS
            personality_tags = ai_agent.personality or []
            speaker_personality = ", ".join(personality_tags) if personality_tags else "无特殊标签"

            prompt = NPC_CHAT_PROMPT.format(
                speaker_nickname=ai_agent.nickname,
                speaker_mbti=ai_agent.mbti or "ISTJ",
                speaker_personality=speaker_personality,
                speaker_career_title=CAREER_LEVELS.get(ai_agent.career_level or 0, {}).get("title", "实习生"),
                speaker_department=ai_agent.department or "unassigned",
                speaker_action=ai_agent.current_action or "idle",
                listener_nickname=me.nickname,
                listener_mbti=me.mbti or "ISTJ",
                listener_career_title=CAREER_LEVELS.get(me.career_level or 0, {}).get("title", "实习生"),
                listener_department=me.department or "unassigned",
                affinity=affinity,
                affinity_label=affinity_label,
                recent_chat_history=chat_history,
                last_message=last_message,
            )

            try:
                llm_result = await call_llm_json(
                    prompt,
                    system_prompt="你是虚拟公司AI角色对话引擎，输出简短自然的回复JSON。",
                    cache_prefix="npc_chat",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "error" not in llm_result:
                    reply_content = llm_result.get("reply", "嗯，好的。")
                else:
                    reply_content = _generate_fallback_reply(ai_agent, me, last_message, affinity)
            except Exception:
                reply_content = _generate_fallback_reply(ai_agent, me, last_message, affinity)

            ai_msg = AgentMessage(
                sender_id=ai_agent_id,
                receiver_id=sender_id,
                content=reply_content,
                msg_type="ai_generated",
            )
            db.add(ai_msg)
            await db.commit()
            await db.refresh(ai_msg)

            # 广播给发送者
            try:
                from app.routers.agent_ws import manager
                await manager.send_to(sender_id, {
                    "type": "new_message",
                    "from": ai_agent_id,
                    "content": reply_content,
                    "msg_id": ai_msg.id,
                    "msg_type": "ai_generated",
                })
            except Exception:
                pass

        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Auto private reply error: %s", e)


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


@router.get("/messages/{agent_id}", response_model=list[MessageOut], summary="聊天记录")
async def get_messages(
    agent_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentMessage)
        .where(
            or_(
                and_(AgentMessage.sender_id == me.id, AgentMessage.receiver_id == agent_id),
                and_(AgentMessage.sender_id == agent_id, AgentMessage.receiver_id == me.id),
            )
        )
        .order_by(AgentMessage.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


@router.post("/send", response_model=MessageOut, summary="发送消息")
async def send_message(
    body: MessageSend,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 限流：每用户每分钟30条
    await check_rate_limit(f"chat_send:{user.id}", max_calls=30, window_seconds=60)

    me = await _get_profile(user, db)
    if me.id == body.receiver_id:
        raise HTTPException(400, "不能给自己发消息")

    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == body.receiver_id)
    )
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(404, "目标角色不存在")

    msg = AgentMessage(
        sender_id=me.id,
        receiver_id=body.receiver_id,
        content=sanitize_text(body.content),
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)

    # 更新好友亲密度 +2 (仅已接受的好友关系)
    friendship_result = await db.execute(
        select(AgentFriendship).where(
            or_(
                and_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == body.receiver_id),
                and_(AgentFriendship.from_id == body.receiver_id, AgentFriendship.to_id == me.id),
            ),
            AgentFriendship.status == "accepted",
        )
    )
    friendship = friendship_result.scalar_one_or_none()
    if friendship:
        friendship.affinity = clamp_affinity((friendship.affinity or 50) + 2)
        await db.flush()

    # 提取聊天记忆
    content_preview = body.content[:50] + ("..." if len(body.content) > 50 else "")
    await extract_memory(
        db, me.id, "chat",
        f"与角色#{body.receiver_id}聊天: {content_preview}",
        related_agent_id=body.receiver_id,
    )

    await db.commit()
    await db.refresh(msg)

    # 如果对方开启了AI自动回复，异步生成回复
    if receiver and receiver.ai_enabled:
        asyncio.create_task(_auto_private_reply(me.id, body.receiver_id, body.content))

    return msg


@router.get("/unread", summary="未读消息数")
async def unread_count(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(sa_func.count(AgentMessage.id)).where(
            AgentMessage.receiver_id == me.id,
            AgentMessage.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"unread": count}


@router.get("/unread-by-sender", summary="按发送者分组的未读消息数")
async def unread_by_sender(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentMessage.sender_id, sa_func.count(AgentMessage.id))
        .where(
            AgentMessage.receiver_id == me.id,
            AgentMessage.is_read == False,
        )
        .group_by(AgentMessage.sender_id)
    )
    return {str(sender_id): count for sender_id, count in result.all()}


@router.post("/read/{agent_id}", summary="标记已读")
async def mark_read(
    agent_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentMessage).where(
            AgentMessage.sender_id == agent_id,
            AgentMessage.receiver_id == me.id,
            AgentMessage.is_read == False,
        )
    )
    messages = result.scalars().all()
    for m in messages:
        m.is_read = True
    await db.flush()
    return {"marked": len(messages)}


# ==================== Agent记忆API ====================

@router.get("/memories", summary="获取Agent记忆列表")
async def get_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    memory_type: str = Query(None, description="记忆类型过滤: interaction/task/observation/career/social"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前Agent的记忆列表，支持分页和类型过滤。
    """
    me = await _get_profile(user, db)

    # 构建查询
    query = select(AgentMemory).where(AgentMemory.agent_id == me.id)
    count_query = select(sa_func.count(AgentMemory.id)).where(AgentMemory.agent_id == me.id)

    if memory_type:
        query = query.where(AgentMemory.memory_type == memory_type)
        count_query = count_query.where(AgentMemory.memory_type == memory_type)

    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    query = query.order_by(
        AgentMemory.importance.desc(),
        AgentMemory.created_at.desc(),
    ).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    memories = result.scalars().all()

    return {
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "memory_type": m.memory_type,
                "importance": m.importance,
                "related_agent_id": m.related_agent_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ],
        "total": total,
    }


@router.get("/memories/summary", summary="获取Agent记忆统计")
async def get_memories_summary(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前Agent的记忆统计摘要。
    """
    me = await _get_profile(user, db)
    summary = await get_memory_summary(db, me.id)
    return summary


# ==================== AI角色自动回复API ====================

# AI回复频率限制：同一对话对3次/分钟
AI_REPLY_RATE_LIMIT_TTL = 60  # 60秒窗口
AI_REPLY_RATE_LIMIT_MAX = 3   # 最多3次


def _get_affinity_label(affinity: int) -> str:
    """将亲密度数值转换为文本标签"""
    if affinity >= 90:
        return "挚友"
    elif affinity >= 70:
        return "好友"
    elif affinity >= 50:
        return "普通朋友"
    elif affinity >= 30:
        return "点头之交"
    else:
        return "陌生人"


@router.post("/ai-reply/{agent_id}", summary="触发AI角色回复")
async def trigger_ai_reply(
    agent_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    当用户向AI-enabled角色发送消息后，触发AI角色自动生成个性化回复。

    限制：
    - 目标角色必须开启ai_enabled
    - 同一对话对每分钟最多3次AI回复
    - 回复内容基于角色MBTI性格、亲密度、对话上下文生成
    """
    me = await _get_profile(user, db)

    # 获取目标AI角色
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    target_agent = result.scalar_one_or_none()
    if not target_agent:
        raise HTTPException(404, "目标角色不存在")

    if not target_agent.ai_enabled:
        raise HTTPException(400, "该角色未启用AI自动回复")

    # ── 频率限制：同一对话对3次/分钟 ──
    pair_key = f"ai_reply_rate:{min(me.id, agent_id)}:{max(me.id, agent_id)}"
    rate_count = await cache_get(pair_key)
    if rate_count is not None and int(rate_count) >= AI_REPLY_RATE_LIMIT_MAX:
        raise HTTPException(429, "AI回复频率过高，请稍后再试")

    # 递增计数
    if rate_count is None:
        await cache_set(pair_key, 1, ttl=AI_REPLY_RATE_LIMIT_TTL)
    else:
        await cache_set(pair_key, int(rate_count) + 1, ttl=AI_REPLY_RATE_LIMIT_TTL)

    # ── 获取对话上下文 ──
    # 最近10条聊天记录
    chat_result = await db.execute(
        select(AgentMessage)
        .where(
            or_(
                and_(AgentMessage.sender_id == me.id, AgentMessage.receiver_id == agent_id),
                and_(AgentMessage.sender_id == agent_id, AgentMessage.receiver_id == me.id),
            )
        )
        .order_by(AgentMessage.created_at.desc())
        .limit(10)
    )
    recent_messages = list(chat_result.scalars().all())
    recent_messages.reverse()

    # 构建对话历史文本
    chat_history_lines = []
    last_message = ""
    for msg in recent_messages:
        if msg.sender_id == me.id:
            sender_name = me.nickname
        else:
            sender_name = target_agent.nickname
        chat_history_lines.append(f"{sender_name}: {msg.content}")
        if msg.sender_id == me.id:
            last_message = msg.content

    chat_history = "\n".join(chat_history_lines[-6:]) if chat_history_lines else "（这是你们的第一次对话）"

    if not last_message:
        last_message = "你好！"

    # ── 获取亲密度 ──
    friendship_result = await db.execute(
        select(AgentFriendship).where(
            or_(
                and_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == agent_id),
                and_(AgentFriendship.from_id == agent_id, AgentFriendship.to_id == me.id),
            ),
            AgentFriendship.status == "accepted",
        )
    )
    friendship = friendship_result.scalar_one_or_none()
    affinity = friendship.affinity if friendship else 30
    affinity_label = _get_affinity_label(affinity)

    # ── 获取角色信息 ──
    speaker_career_title = CAREER_LEVELS.get(target_agent.career_level or 0, {}).get("title", "实习生")
    listener_career_title = CAREER_LEVELS.get(me.career_level or 0, {}).get("title", "实习生")

    personality_tags = target_agent.personality if target_agent.personality else []
    speaker_personality = ", ".join(personality_tags) if personality_tags else "无特殊标签"

    # ── 构建Prompt并调用LLM ──
    prompt = NPC_CHAT_PROMPT.format(
        speaker_nickname=target_agent.nickname,
        speaker_mbti=target_agent.mbti or "ISTJ",
        speaker_personality=speaker_personality,
        speaker_career_title=speaker_career_title,
        speaker_department=target_agent.department or "unassigned",
        speaker_action=target_agent.current_action or "idle",
        listener_nickname=me.nickname,
        listener_mbti=me.mbti or "ISTJ",
        listener_career_title=listener_career_title,
        listener_department=me.department or "unassigned",
        affinity=affinity,
        affinity_label=affinity_label,
        recent_chat_history=chat_history,
        last_message=last_message,
    )

    try:
        llm_result = await call_llm_json(
            prompt,
            system_prompt="你是一个虚拟公司AI角色对话引擎。请严格按照要求输出JSON格式的回复。",
            cache_prefix="npc_chat",
            use_cache=False,  # 对话不缓存，每次生成新回复
        )

        if isinstance(llm_result, dict) and "error" in llm_result:
            # LLM调用失败，使用简单回退回复
            reply_content = _generate_fallback_reply(target_agent, me, last_message, affinity)
            emotion = "neutral"
            action_hint = ""
        else:
            reply_content = llm_result.get("reply", "嗯，好的。")
            emotion = llm_result.get("emotion", "neutral")
            action_hint = llm_result.get("action_hint", "")

    except Exception:
        reply_content = _generate_fallback_reply(target_agent, me, last_message, affinity)
        emotion = "neutral"
        action_hint = ""

    # ── 保存AI回复消息 ──
    ai_msg = AgentMessage(
        sender_id=agent_id,
        receiver_id=me.id,
        content=reply_content,
        msg_type="ai_generated",
    )
    db.add(ai_msg)
    await db.flush()
    await db.refresh(ai_msg)

    # ── 提取AI角色的聊天记忆 ──
    content_preview = reply_content[:50] + ("..." if len(reply_content) > 50 else "")
    try:
        await extract_memory(
            db, agent_id, "chat",
            f"与{me.nickname}聊天，回复了: {content_preview}",
            related_agent_id=me.id,
        )
    except Exception:
        pass

    # ── 更新亲密度 +1 ──
    if friendship:
        new_affinity = min(100, (friendship.affinity or 50) + 1)
        friendship.affinity = new_affinity

    await db.commit()

    return {
        "message": {
            "id": ai_msg.id,
            "sender_id": ai_msg.sender_id,
            "receiver_id": ai_msg.receiver_id,
            "content": ai_msg.content,
            "msg_type": ai_msg.msg_type,
            "is_read": ai_msg.is_read,
            "created_at": ai_msg.created_at.isoformat() if ai_msg.created_at else None,
        },
        "emotion": emotion,
        "action_hint": action_hint,
    }


def _generate_fallback_reply(
    speaker: AgentProfile,
    listener: AgentProfile,
    last_message: str,
    affinity: int,
) -> str:
    """当LLM调用失败时，生成基于MBTI的简单回退回复"""
    import random

    mbti = speaker.mbti or "ISTJ"

    # 根据外向/内向选择回复风格
    if mbti[0] == "E":
        greetings = [
            f"哈哈，{listener.nickname}你说得对！",
            "我正好也想聊聊这个！",
            "太好了，我们找个时间好好聊！",
            f"嘿{listener.nickname}，有什么新鲜事吗？",
        ]
    else:
        greetings = [
            "嗯，我知道了。",
            "好的，我想想。",
            "有道理。",
            "嗯...让我考虑一下。",
        ]

    # 高亲密度用更亲近的语气
    if affinity >= 70:
        greetings.extend([
            f"好啊{listener.nickname}！",
            "哈哈，跟你聊天总是很开心~",
        ])
    elif affinity < 30:
        greetings = [
            "你好。",
            "嗯，好的。",
            "了解了。",
        ]

    return random.choice(greetings)
