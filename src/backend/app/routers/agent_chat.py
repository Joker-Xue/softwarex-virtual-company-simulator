"""
chatSystem API
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
    """DirectAI automatically replies to background Tasks - running in a standalone DBsession"""
    await asyncio.sleep(random.uniform(1.5, 4.0))  # Simulate Thinking Delay

    async with AsyncSessionLocal() as db:
        try:
            # Load two profile info
            me_result = await db.execute(select(AgentProfile).where(AgentProfile.id == sender_id))
            ai_result = await db.execute(select(AgentProfile).where(AgentProfile.id == ai_agent_id))
            me = me_result.scalar_one_or_none()
            ai_agent = ai_result.scalar_one_or_none()
            if not me or not ai_agent or not ai_agent.ai_enabled:
                return

            # Get recent conversation context
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
            chat_history = "\n".join(history_lines[-6:]) if history_lines else "（This is the first conversation）"

            # Get affinity
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
            speaker_personality = ", ".join(personality_tags) if personality_tags else "No special label"

            prompt = NPC_CHAT_PROMPT.format(
                speaker_nickname=ai_agent.nickname,
                speaker_mbti=ai_agent.mbti or "ISTJ",
                speaker_personality=speaker_personality,
                speaker_career_title=CAREER_LEVELS.get(ai_agent.career_level or 0, {}).get("title", "Intern"),
                speaker_department=ai_agent.department or "unassigned",
                speaker_action=ai_agent.current_action or "idle",
                listener_nickname=me.nickname,
                listener_mbti=me.mbti or "ISTJ",
                listener_career_title=CAREER_LEVELS.get(me.career_level or 0, {}).get("title", "Intern"),
                listener_department=me.department or "unassigned",
                affinity=affinity,
                affinity_label=affinity_label,
                recent_chat_history=chat_history,
                last_message=last_message,
            )

            try:
                llm_result = await call_llm_json(
                    prompt,
                    system_prompt="you are virtual companyAICharacter dialogue engine，Output a short and natural reply JSON.",
                    cache_prefix="npc_chat",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "error" not in llm_result:
                    reply_content = llm_result.get("reply", "Um，OK。")
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

            # Broadcast to sender
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
        raise HTTPException(404, "Profile has not been created yet")
    return profile


@router.get("/messages/{agent_id}", response_model=list[MessageOut], summary="Chat History")
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


@router.post("/send", response_model=MessageOut, summary="Send Message")
async def send_message(
    body: MessageSend,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # rate limit：30 msgs per user per minute
    await check_rate_limit(f"chat_send:{user.id}", max_calls=30, window_seconds=60)

    me = await _get_profile(user, db)
    if me.id == body.receiver_id:
        raise HTTPException(400, "Can't give myself a message")

    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == body.receiver_id)
    )
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(404, "Target profile does not exist")

    msg = AgentMessage(
        sender_id=me.id,
        receiver_id=body.receiver_id,
        content=sanitize_text(body.content),
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)

    # Update friendaffinity +2 (Only accepted friend relationships)
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

    # Extract chatMemories
    content_preview = body.content[:50] + ("..." if len(body.content) > 50 else "")
    await extract_memory(
        db, me.id, "chat",
        f"with Role#{body.receiver_id}chat: {content_preview}",
        related_agent_id=body.receiver_id,
    )

    await db.commit()
    await db.refresh(msg)

    # If the other party has enabled AI automatic reply，Generate reply asynchronously
    if receiver and receiver.ai_enabled:
        asyncio.create_task(_auto_private_reply(me.id, body.receiver_id, body.content))

    return msg


@router.get("/unread", summary="Number of unread information")
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


@router.get("/unread-by-sender", summary="Number of unread messages grouped by sender")
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


@router.post("/read/{agent_id}", summary="mark has read")
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


# ==================== AgentMemoriesAPI ====================

@router.get("/memories", summary="Get the list of AgentMemories")
async def get_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    memory_type: str = Query(None, description="Memoriestypefilter: interaction/task/observation/career/social"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the Memories list of CurrentAgent，Supports paging and typefilter.
    """
    me = await _get_profile(user, db)

    # Build query
    query = select(AgentMemory).where(AgentMemory.agent_id == me.id)
    count_query = select(sa_func.count(AgentMemory.id)).where(AgentMemory.agent_id == me.id)

    if memory_type:
        query = query.where(AgentMemory.memory_type == memory_type)
        count_query = count_query.where(AgentMemory.memory_type == memory_type)

    # Get total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Page query
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


@router.get("/memories/summary", summary="Get AgentMemories statistics")
async def get_memories_summary(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a summary of CurrentAgent's Memories statistics。
    """
    me = await _get_profile(user, db)
    summary = await get_memory_summary(db, me.id)
    return summary


# ==================== AIRole automatic reply API ====================

# AI reply frequency limit：Same conversation pair 3 times/minutes
AI_REPLY_RATE_LIMIT_TTL = 60  # 60 second window
AI_REPLY_RATE_LIMIT_MAX = 3   # Up to 3 times


def _get_affinity_label(affinity: int) -> str:
    """Convert affinity value to text label"""
    if affinity >= 90:
        return "best friend"
    elif affinity >= 70:
        return "friend"
    elif affinity >= 50:
        return "ordinary friends"
    elif affinity >= 30:
        return "acquaintance"
    else:
        return "stranger"


@router.post("/ai-reply/{agent_id}", summary="Trigger AIRole reply")
async def trigger_ai_reply(
    agent_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    When the user sends to the AI-enabled role After Message，Trigger AI characters to automatically generate personalized responses。

    limit：
    - The target character must have ai_enabled turned on
    - The same conversation can have up to 3 AI replies per minute.
    - Reply content based on role MBTIpersonality、affinity、Dialogue context generation
    """
    me = await _get_profile(user, db)

    # Get target AIRole
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    target_agent = result.scalar_one_or_none()
    if not target_agent:
        raise HTTPException(404, "Target profile does not exist")

    if not target_agent.ai_enabled:
        raise HTTPException(400, "AI automatic reply is not enabled for this role")

    # ── Frequency limit：Same conversation pair 3 times/minutes ──
    pair_key = f"ai_reply_rate:{min(me.id, agent_id)}:{max(me.id, agent_id)}"
    rate_count = await cache_get(pair_key)
    if rate_count is not None and int(rate_count) >= AI_REPLY_RATE_LIMIT_MAX:
        raise HTTPException(429, "AI replies too frequently，Please try again later")

    # Count up
    if rate_count is None:
        await cache_set(pair_key, 1, ttl=AI_REPLY_RATE_LIMIT_TTL)
    else:
        await cache_set(pair_key, int(rate_count) + 1, ttl=AI_REPLY_RATE_LIMIT_TTL)

    # ── Get conversation context ──
    # Recent 10 msgsChat History
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

    # Construct conversation history text
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

    chat_history = "\n".join(chat_history_lines[-6:]) if chat_history_lines else "（This is your first conversation）"

    if not last_message:
        last_message = "Hello！"

    # ── Get affinity ──
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

    # ── Get profile info
    speaker_career_title = CAREER_LEVELS.get(target_agent.career_level or 0, {}).get("title", "Intern")
    listener_career_title = CAREER_LEVELS.get(me.career_level or 0, {}).get("title", "Intern")

    personality_tags = target_agent.personality if target_agent.personality else []
    speaker_personality = ", ".join(personality_tags) if personality_tags else "No special label"

    # ── Build Prompt and call LLM ──
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
            system_prompt="you are a virtual companyAICharacter dialogue engine。Please strictly follow the requirements to output the response in JSON format.。",
            cache_prefix="npc_chat",
            use_cache=False,  # Conversations are not cached，Generate new reply every time
        )

        if isinstance(llm_result, dict) and "error" in llm_result:
            # LLM call failed，Use simple fallback reply
            reply_content = _generate_fallback_reply(target_agent, me, last_message, affinity)
            emotion = "neutral"
            action_hint = ""
        else:
            reply_content = llm_result.get("reply", "Um，OK。")
            emotion = llm_result.get("emotion", "neutral")
            action_hint = llm_result.get("action_hint", "")

    except Exception:
        reply_content = _generate_fallback_reply(target_agent, me, last_message, affinity)
        emotion = "neutral"
        action_hint = ""

    # ── Save AI reply information
    ai_msg = AgentMessage(
        sender_id=agent_id,
        receiver_id=me.id,
        content=reply_content,
        msg_type="ai_generated",
    )
    db.add(ai_msg)
    await db.flush()
    await db.refresh(ai_msg)

    # ── Extract chat memories of AI characters ──
    content_preview = reply_content[:50] + ("..." if len(reply_content) > 50 else "")
    try:
        await extract_memory(
            db, agent_id, "chat",
            f"chat with {me.nickname}，Replied: {content_preview}",
            related_agent_id=me.id,
        )
    except Exception:
        pass

    # ── Update affinity +1
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
    """When LLM call fails，Generate a simple fallback response based on MBTI"""
    import random

    mbti = speaker.mbti or "ISTJ"

    # Choose reply style according to Extraversion/Introversion
    if mbti[0] == "E":
        greetings = [
            f"Ha ha，{listener.nickname}you're right！",
            "I just want to talk about this too！",
            "Very good，Let's find a time to chat！",
            f"Hey {listener.nickname}，What's new?？",
        ]
    else:
        greetings = [
            "Um，I see。",
            "Got it, Let me think about it。",
            "Makes sense。",
            "Hmm...let me think about it。",
        ]

    # High affinity uses a more intimate tone
    if affinity >= 70:
        greetings.extend([
            f"OK {listener.nickname}！",
            "Ha ha，It's always fun to chat with you~",
        ])
    elif affinity < 30:
        greetings = [
            "Hello。",
            "Um，OK。",
            "Understood。",
        ]

    return random.choice(greetings)
