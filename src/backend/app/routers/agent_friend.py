"""
friendSystem API
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
    """NPC automatically applies through friend（5 seconds delay，Simulate counterparty review）"""
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

            # Get NPCNickname for notification
            npc_result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == friendship.to_id)
            )
            npc = npc_result.scalar_one_or_none()
            npc_nickname = npc.nickname if npc else "NPC"

            # Push friend to notify the applicant
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
    """Detection Tutor/Student Relationship: If Level Gap >= 2，The higher one is mentor，The lower one is mentee"""
    diff = friend_level - my_level
    if diff >= 2:
        return "mentor"   # The other person is my mentor
    elif diff <= -2:
        return "mentee"   # The other party is my student
    return ""


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")
    return profile


@router.post("/request/{agent_id}", summary="Send Friend Request")
async def send_request(
    agent_id: int,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # rate limit：10 times per user per hour
    await check_rate_limit(f"friend_req:{user.id}", max_calls=10, window_seconds=3600)

    me = await _get_profile(user, db)
    if me.id == agent_id:
        raise HTTPException(400, "Can't add myself as friend")

    # Check target exists
    result = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Target profile does not exist")

    # Check if there is an existing relationship
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
            raise HTTPException(400, "Already a friend")
        if existing.status == "pending":
            raise HTTPException(400, "There is already a pending friend request")

    friendship = AgentFriendship(from_id=me.id, to_id=agent_id)
    db.add(friendship)
    await db.flush()
    await db.commit()

    # NPC passes automatically：If the opponent is an AI character，Automatically accept after 10 seconds
    if target.ai_enabled:
        asyncio.create_task(_npc_auto_accept(friendship.id))

    return {"message": "friendaskSend", "id": friendship.id}


@router.post("/accept/{friendship_id}", summary="acceptfriendask")
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
        raise HTTPException(404, "friendRequest does not exist")

    friendship.status = "accepted"
    friendship.accepted_at = datetime.now(timezone.utc)
    await db.flush()

    # ExtractSocialMemories（Both sides record）
    # Get the Nickname of the initiator
    sender_result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == friendship.from_id)
    )
    sender = sender_result.scalar_one_or_none()
    sender_name = sender.nickname if sender else f"Role#{friendship.from_id}"

    await extract_memory(
        db, me.id, "friendship",
        f"accept{sender_name}friend request，become friends",
        related_agent_id=friendship.from_id,
    )
    await extract_memory(
        db, friendship.from_id, "friendship",
        f"{me.nickname}acceptfriendask，become friends",
        related_agent_id=me.id,
    )

    return {"message": "Friend request has been accepted"}


@router.post("/reject/{friendship_id}", summary="rejectfriendask")
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
        raise HTTPException(404, "friendRequest does not exist")

    friendship.status = "rejected"
    await db.flush()
    return {"message": "Rejected friend request"}


@router.get("/list", response_model=list[FriendshipOut], summary="Friend List")
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

        # Calculate MBTI compatibility
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


@router.get("/compatibility/{agent_id}", summary="friendcompatible sex details")
async def friend_compatibility(
    agent_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed MBTI compatible information with the specified friend"""
    me = await _get_profile(user, db)

    # Confirmed to be a friend
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
        raise HTTPException(404, "friendrelationship does not exist")

    # Get friendprofile
    r = await db.execute(select(AgentProfile).where(AgentProfile.id == agent_id))
    friend = r.scalar_one_or_none()
    if not friend:
        raise HTTPException(404, "friendrole does not exist")

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


@router.get("/pending", summary="Pendingfriend request")
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


@router.delete("/{friendship_id}", summary="delete friend")
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
        raise HTTPException(404, "friendrelationship does not exist")

    await db.delete(friendship)
    await db.flush()
    return {"message": "friend deleted"}


@router.get("/sent", summary="The friend application I sent（Contains status）")
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


@router.get("/received", summary="All friend requests received（Contains status）")
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
