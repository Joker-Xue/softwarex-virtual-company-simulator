"""
好友系统API
"""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from app.database import get_db, AsyncSessionLocal
from app.utils.security import get_current_active_user
from app.utils.rate_limit import check_rate_limit
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_friendship import AgentFriendship
from app.schemas.agent_social import FriendshipOut, CompatibilityDetail
from app.engine.mbti_compat import get_compatibility, get_compatibility_label, get_compatibility_tips
from app.engine.memory_engine import extract_memory

router = APIRouter()


async def _npc_auto_accept(friendship_id: int):
    """NPC自动通过好友申请（5秒延迟，模拟对方审核）"""
    await asyncio.sleep(5)
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(AgentFriendship).where(
                    AgentFriendship.id == friendship_id,
                    AgentFriendship.status == "pending",
                )
            )
            friendship = result.scalar_one_or_none()
            if not friendship:
                return
            friendship.status = "accepted"
            friendship.accepted_at = datetime.now(timezone.utc)
            await db.commit()

            # 获取NPC昵称用于通知
            npc_result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == friendship.to_id)
            )
            npc = npc_result.scalar_one_or_none()
            npc_nickname = npc.nickname if npc else "NPC"

            # 推送好友通过通知给申请人
            try:
                from app.routers.agent_ws import manager
                await manager.send_to(friendship.from_id, {
                    "type": "friend_accepted",
                    "friendship_id": friendship.id,
                    "from_id": friendship.from_id,
                    "to_id": friendship.to_id,
                    "nickname": npc_nickname,
                })
            except Exception:
                pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("NPC auto-accept failed: %s", e)


def _detect_role(my_level: int, friend_level: int) -> str:
    """检测导师/学员关系: 如果职级差距 >= 2，较高者为mentor，较低者为mentee"""
    diff = friend_level - my_level
    if diff >= 2:
        return "mentor"   # 对方是我的导师
    elif diff <= -2:
        return "mentee"   # 对方是我的学员
    return ""


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


@router.post("/request/{agent_id}", summary="发送好友请求")
async def send_request(
    agent_id: int,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 限流：每用户每小时10次
    await check_rate_limit(f"friend_req:{user.id}", max_calls=10, window_seconds=3600)

    me = await _get_profile(user, db)
    if me.id == agent_id:
        raise HTTPException(400, "不能添加自己为好友")

    # 检查目标存在
    result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "目标角色不存在")

    # 检查是否已有关系
    result = await db.execute(
        select(AgentFriendship).where(
            or_(
                and_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == agent_id),
                and_(AgentFriendship.from_id == agent_id, AgentFriendship.to_id == me.id),
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.status == "accepted":
            raise HTTPException(400, "已经是好友了")
        if existing.status == "pending":
            raise HTTPException(400, "已有待处理的好友请求")

    friendship = AgentFriendship(from_id=me.id, to_id=agent_id)
    db.add(friendship)
    await db.flush()
    await db.commit()

    # NPC自动通过：如果对方是AI角色，10秒后自动接受
    if target.ai_enabled:
        asyncio.create_task(_npc_auto_accept(friendship.id))

    return {"message": "好友请求已发送", "id": friendship.id}


@router.post("/accept/{friendship_id}", summary="接受好友请求")
async def accept_request(
    friendship_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.id == friendship_id,
            AgentFriendship.to_id == me.id,
            AgentFriendship.status == "pending",
        )
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        raise HTTPException(404, "好友请求不存在")

    friendship.status = "accepted"
    friendship.accepted_at = datetime.now(timezone.utc)
    await db.flush()

    # 提取社交记忆（双方都记录）
    # 获取发起方昵称
    sender_result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == friendship.from_id)
    )
    sender = sender_result.scalar_one_or_none()
    sender_name = sender.nickname if sender else f"角色#{friendship.from_id}"

    await extract_memory(
        db, me.id, "friendship",
        f"接受了{sender_name}的好友请求，成为好友",
        related_agent_id=friendship.from_id,
    )
    await extract_memory(
        db, friendship.from_id, "friendship",
        f"{me.nickname}接受了好友请求，成为好友",
        related_agent_id=me.id,
    )

    return {"message": "已接受好友请求"}


@router.post("/reject/{friendship_id}", summary="拒绝好友请求")
async def reject_request(
    friendship_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.id == friendship_id,
            AgentFriendship.to_id == me.id,
            AgentFriendship.status == "pending",
        )
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        raise HTTPException(404, "好友请求不存在")

    friendship.status = "rejected"
    await db.flush()
    return {"message": "已拒绝好友请求"}


@router.get("/list", response_model=list[FriendshipOut], summary="好友列表")
async def friend_list(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship).where(
            or_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == me.id),
            AgentFriendship.status == "accepted",
        )
    )
    friendships = result.scalars().all()

    out = []
    for f in friendships:
        friend_id = f.to_id if f.from_id == me.id else f.from_id
        r = await db.execute(select(AgentProfile).where(AgentProfile.id == friend_id))
        friend = r.scalar_one_or_none()

        # 计算MBTI兼容性
        compat_score = 0.0
        compat_label = ""
        role = ""
        friend_mbti = ""
        friend_dept = ""
        if friend:
            friend_mbti = friend.mbti or ""
            friend_dept = friend.department or ""
            if me.mbti and friend.mbti:
                compat_score = get_compatibility(me.mbti, friend.mbti)
                compat_label = get_compatibility_label(compat_score)
            role = _detect_role(me.career_level, friend.career_level)

        out.append(FriendshipOut(
            id=f.id,
            from_id=f.from_id,
            to_id=f.to_id,
            status=f.status,
            created_at=f.created_at,
            accepted_at=f.accepted_at,
            friend_nickname=friend.nickname if friend else "",
            friend_avatar=friend.avatar_key if friend else "",
            friend_level=friend.career_level if friend else 0,
            friend_department=friend_dept,
            friend_mbti=friend_mbti,
            affinity=f.affinity if f.affinity is not None else 50,
            compatibility_score=round(compat_score, 2),
            compatibility_label=compat_label,
            role=role,
        ))
    return out


@router.get("/compatibility/{agent_id}", summary="好友兼容性详情")
async def friend_compatibility(
    agent_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取与指定好友的详细MBTI兼容性信息"""
    me = await _get_profile(user, db)

    # 确认是好友
    result = await db.execute(
        select(AgentFriendship).where(
            or_(
                and_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == agent_id),
                and_(AgentFriendship.from_id == agent_id, AgentFriendship.to_id == me.id),
            ),
            AgentFriendship.status == "accepted",
        )
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        raise HTTPException(404, "好友关系不存在")

    # 获取好友profile
    r = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    friend = r.scalar_one_or_none()
    if not friend:
        raise HTTPException(404, "好友角色不存在")

    mbti_a = me.mbti or "ISTJ"
    mbti_b = friend.mbti or "ISTJ"
    compat_score = get_compatibility(mbti_a, mbti_b)
    compat_label = get_compatibility_label(compat_score)
    tips = get_compatibility_tips(mbti_a, mbti_b)
    role = _detect_role(me.career_level, friend.career_level)

    return CompatibilityDetail(
        friend_id=agent_id,
        friend_nickname=friend.nickname,
        mbti_a=mbti_a,
        mbti_b=mbti_b,
        compatibility_score=round(compat_score, 2),
        compatibility_label=compat_label,
        tips=tips,
        role=role,
    )


@router.get("/pending", summary="待处理的好友请求")
async def pending_requests(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.to_id == me.id,
            AgentFriendship.status == "pending",
        )
    )
    friendships = result.scalars().all()
    out = []
    for f in friendships:
        r = await db.execute(select(AgentProfile).where(AgentProfile.id == f.from_id))
        sender = r.scalar_one_or_none()
        out.append({
            "id": f.id,
            "from_id": f.from_id,
            "nickname": sender.nickname if sender else "",
            "avatar_key": sender.avatar_key if sender else "",
            "created_at": f.created_at,
        })
    return out


@router.delete("/{friendship_id}", summary="删除好友")
async def delete_friend(
    friendship_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship).where(
            AgentFriendship.id == friendship_id,
            or_(AgentFriendship.from_id == me.id, AgentFriendship.to_id == me.id),
        )
    )
    friendship = result.scalar_one_or_none()
    if not friendship:
        raise HTTPException(404, "好友关系不存在")

    await db.delete(friendship)
    await db.flush()
    return {"message": "已删除好友"}


@router.get("/sent", summary="我发出的好友申请（含状态）")
async def sent_requests(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship)
        .where(AgentFriendship.from_id == me.id)
        .order_by(AgentFriendship.created_at.desc())
    )
    friendships = result.scalars().all()
    out = []
    for f in friendships:
        r = await db.execute(select(AgentProfile).where(AgentProfile.id == f.to_id))
        target = r.scalar_one_or_none()
        out.append({
            "id": f.id,
            "to_id": f.to_id,
            "nickname": target.nickname if target else "",
            "avatar_key": target.avatar_key if target else "",
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "accepted_at": f.accepted_at.isoformat() if f.accepted_at else None,
        })
    return out


@router.get("/received", summary="收到的所有好友申请（含状态）")
async def received_requests(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)
    result = await db.execute(
        select(AgentFriendship)
        .where(AgentFriendship.to_id == me.id)
        .order_by(AgentFriendship.created_at.desc())
    )
    friendships = result.scalars().all()
    out = []
    for f in friendships:
        r = await db.execute(select(AgentProfile).where(AgentProfile.id == f.from_id))
        sender = r.scalar_one_or_none()
        out.append({
            "id": f.id,
            "from_id": f.from_id,
            "nickname": sender.nickname if sender else "",
            "avatar_key": sender.avatar_key if sender else "",
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        })
    return out
