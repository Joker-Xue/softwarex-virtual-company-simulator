"""
群聊与频道API
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from pydantic import BaseModel, Field
from typing import List, Optional

from app.database import get_db
from app.utils.security import get_current_active_user
from app.utils.sanitize import sanitize_text
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_message import AgentMessage

router = APIRouter()

# 预置部门频道
PRESET_CHANNELS = [
    {"id": "dept_engineering", "name": "工程部频道", "type": "department"},
    {"id": "dept_marketing", "name": "市场部频道", "type": "department"},
    {"id": "dept_finance", "name": "财务部频道", "type": "department"},
    {"id": "dept_hr", "name": "HR部门频道", "type": "department"},
    {"id": "announcement", "name": "全公司公告", "type": "announcement"},
]


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    member_ids: List[int] = Field(..., min_length=1)


class GroupMessageSend(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class GroupInfo(BaseModel):
    group_id: str
    name: str
    group_type: str  # custom / department / announcement
    member_count: int
    members: List[dict] = []


class GroupMessageOut(BaseModel):
    id: int
    sender_id: int
    sender_nickname: str = ""
    sender_avatar: str = ""
    content: str
    msg_type: str
    created_at: Optional[str] = None


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


@router.post("/group/create", summary="创建群聊")
async def create_group(
    body: GroupCreateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # 生成群聊ID
    import uuid
    group_id = f"grp_{uuid.uuid4().hex[:12]}"

    # 验证成员存在
    member_ids = list(set(body.member_ids))
    if me.id not in member_ids:
        member_ids.append(me.id)

    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id.in_(member_ids))
    )
    members = result.scalars().all()
    if len(members) < 2:
        raise HTTPException(400, "群聊至少需要2个成员")

    # 发送系统消息宣布群聊创建
    sys_msg = AgentMessage(
        sender_id=me.id,
        receiver_id=me.id,
        content=f"{me.nickname} 创建了群聊「{body.name}」",
        msg_type="system",
        group_id=group_id,
    )
    db.add(sys_msg)

    # 记录群元信息到第一条消息（简化方案，不需要额外表）
    meta_msg = AgentMessage(
        sender_id=me.id,
        receiver_id=me.id,
        content=f"__GROUP_META__|{body.name}|{','.join(str(m.id) for m in members)}",
        msg_type="system",
        group_id=group_id,
    )
    db.add(meta_msg)
    await db.flush()

    return {
        "group_id": group_id,
        "name": body.name,
        "member_count": len(members),
        "members": [{"id": m.id, "nickname": m.nickname, "avatar_key": m.avatar_key} for m in members],
    }


@router.post("/group/{group_id}/send", summary="群发消息")
async def send_group_message(
    group_id: str,
    body: GroupMessageSend,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # 验证群聊存在
    result = await db.execute(
        select(AgentMessage).where(
            AgentMessage.group_id == group_id,
        ).limit(1)
    )
    if not result.scalar_one_or_none():
        # 检查是否是预置频道
        if not any(ch["id"] == group_id for ch in PRESET_CHANNELS):
            raise HTTPException(404, "群聊不存在")

    msg = AgentMessage(
        sender_id=me.id,
        receiver_id=None,  # 群消息receiver_id=None
        content=sanitize_text(body.content),
        msg_type="text",
        group_id=group_id,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)

    # 部门频道：随机触发NPC回复
    is_dept_channel = group_id.startswith("dept_")
    if is_dept_channel:
        department = group_id.replace("dept_", "")
        asyncio.create_task(
            _trigger_channel_reply(group_id, me.id, body.content, department)
        )

    return {
        "id": msg.id,
        "sender_id": me.id,
        "sender_nickname": me.nickname,
        "sender_avatar": me.avatar_key,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


@router.get("/group/{group_id}/messages", summary="群消息历史")
async def get_group_messages(
    group_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.group_id == group_id)
        .order_by(AgentMessage.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    # 获取发送者信息
    sender_ids = list(set(m.sender_id for m in messages))
    sender_map = {}
    if sender_ids:
        sr = await db.execute(
            select(AgentProfile).where(AgentProfile.id.in_(sender_ids))
        )
        for p in sr.scalars().all():
            sender_map[p.id] = {"nickname": p.nickname, "avatar_key": p.avatar_key}

    return [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_nickname": sender_map.get(m.sender_id, {}).get("nickname", ""),
            "sender_avatar": sender_map.get(m.sender_id, {}).get("avatar_key", ""),
            "content": m.content,
            "msg_type": m.msg_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
        if m.msg_type != "system" or not m.content.startswith("__GROUP_META__")
    ]


@router.get("/groups", summary="我的群聊列表")
async def my_groups(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # 查找我参与的群聊（发过消息的群）
    result = await db.execute(
        select(AgentMessage.group_id)
        .where(
            AgentMessage.sender_id == me.id,
            AgentMessage.group_id.isnot(None),
        )
        .distinct()
    )
    my_group_ids = [row[0] for row in result.all()]

    groups = []

    # 预置频道（根据部门自动加入）
    for ch in PRESET_CHANNELS:
        if ch["type"] == "announcement" or (
            ch["type"] == "department" and ch["id"] == f"dept_{me.department}"
        ):
            # 统计消息数
            count_result = await db.execute(
                select(sa_func.count(AgentMessage.id)).where(
                    AgentMessage.group_id == ch["id"]
                )
            )
            msg_count = count_result.scalar() or 0
            groups.append({
                "group_id": ch["id"],
                "name": ch["name"],
                "group_type": ch["type"],
                "message_count": msg_count,
            })

    # 自定义群聊
    for gid in my_group_ids:
        if any(ch["id"] == gid for ch in PRESET_CHANNELS):
            continue
        # 获取群元信息
        meta_result = await db.execute(
            select(AgentMessage).where(
                AgentMessage.group_id == gid,
                AgentMessage.msg_type == "system",
                AgentMessage.content.like("__GROUP_META__%"),
            ).limit(1)
        )
        meta = meta_result.scalar_one_or_none()
        name = gid
        if meta:
            parts = meta.content.split("|")
            if len(parts) >= 2:
                name = parts[1]

        count_result = await db.execute(
            select(sa_func.count(AgentMessage.id)).where(
                AgentMessage.group_id == gid,
                AgentMessage.msg_type != "system",
            )
        )
        msg_count = count_result.scalar() or 0
        groups.append({
            "group_id": gid,
            "name": name,
            "group_type": "custom",
            "message_count": msg_count,
        })

    return groups


async def _trigger_channel_reply(group_id: str, user_sender_id: int, user_message: str, department: str):
    """以50%概率触发NPC在频道中回复用户消息"""
    import random
    if random.random() > 0.5:  # 50%概率回复，避免每条消息都有回复
        return
    try:
        from app.engine.channel_engine import post_channel_reply
        await post_channel_reply(group_id, user_sender_id, user_message, department)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Channel reply trigger error: %s", e)
