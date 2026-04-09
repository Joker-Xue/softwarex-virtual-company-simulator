"""
会议室预约系统API
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.meeting_booking import MeetingBooking
from app.models.company_room import CompanyRoom
from app.engine.memory_engine import extract_memory

router = APIRouter()


# ── Schemas ──

class MeetingCreate(BaseModel):
    room_id: int
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    start_time: datetime
    duration_minutes: int = Field(60, ge=30, le=90)
    participant_ids: List[int] = []


class MeetingOut(BaseModel):
    id: int
    room_id: int
    organizer_id: int
    organizer_name: str = ""
    room_name: str = ""
    title: str
    description: str
    start_time: datetime
    duration_minutes: int
    participant_ids: List[int]
    status: str
    xp_reward: int
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Helpers ──

async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


# ── Endpoints ──

@router.get("/list", summary="会议预约列表")
async def list_meetings(
    status: str = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    q = select(MeetingBooking).order_by(MeetingBooking.start_time.desc())
    if status:
        q = q.where(MeetingBooking.status == status)
    result = await db.execute(q)
    bookings = result.scalars().all()

    # 丰富展示数据
    room_ids = {b.room_id for b in bookings}
    organizer_ids = {b.organizer_id for b in bookings}

    rooms_result = await db.execute(select(CompanyRoom).where(CompanyRoom.id.in_(room_ids))) if room_ids else None
    rooms_map = {r.id: r.name for r in rooms_result.scalars().all()} if rooms_result else {}

    org_result = await db.execute(select(AgentProfile).where(AgentProfile.id.in_(organizer_ids))) if organizer_ids else None
    org_map = {p.id: p.nickname for p in org_result.scalars().all()} if org_result else {}

    return [
        {
            "id": b.id,
            "room_id": b.room_id,
            "room_name": rooms_map.get(b.room_id, ""),
            "organizer_id": b.organizer_id,
            "organizer_name": org_map.get(b.organizer_id, ""),
            "title": b.title,
            "description": b.description,
            "start_time": b.start_time,
            "duration_minutes": b.duration_minutes,
            "participant_ids": b.participant_ids or [],
            "status": b.status,
            "xp_reward": b.xp_reward,
            "created_at": b.created_at,
            "is_mine": b.organizer_id == me.id or me.id in (b.participant_ids or []),
        }
        for b in bookings
    ]


@router.post("/create", summary="预约会议室")
async def create_meeting(
    body: MeetingCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # 验证房间存在且是会议室
    room_result = await db.execute(
        select(CompanyRoom).where(CompanyRoom.id == body.room_id)
    )
    room = room_result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "房间不存在")
    if room.room_type not in ("meeting", "office", "ceo_office"):
        raise HTTPException(400, "该房间不支持预约会议")

    # 验证时间不在过去
    if body.start_time < datetime.now(timezone.utc):
        raise HTTPException(400, "会议开始时间不能在过去")

    # 验证无时间冲突
    end_time = body.start_time + timedelta(minutes=body.duration_minutes)
    conflict_result = await db.execute(
        select(MeetingBooking).where(
            MeetingBooking.room_id == body.room_id,
            MeetingBooking.status.in_(["scheduled", "in_progress"]),
            MeetingBooking.start_time < end_time,
            # start_time + duration > body.start_time
        )
    )
    conflicts = conflict_result.scalars().all()
    for c in conflicts:
        c_end = c.start_time + timedelta(minutes=c.duration_minutes)
        if body.start_time < c_end and end_time > c.start_time:
            raise HTTPException(409, f"与已有会议「{c.title}」时间冲突")

    # 验证参与者存在
    all_participants = list(set([me.id] + body.participant_ids))
    if len(all_participants) > room.capacity:
        raise HTTPException(400, f"参与人数超过房间容量({room.capacity})")

    booking = MeetingBooking(
        room_id=body.room_id,
        organizer_id=me.id,
        title=body.title,
        description=body.description,
        start_time=body.start_time,
        duration_minutes=body.duration_minutes,
        participant_ids=all_participants,
        xp_reward=15 + len(all_participants) * 5,
    )
    db.add(booking)
    await db.flush()
    await db.refresh(booking)

    # 记忆
    await extract_memory(
        db, me.id, "task_complete",
        f"预约了会议「{body.title}」，邀请了{len(all_participants) - 1}位同事",
    )

    return {
        "id": booking.id,
        "message": "会议预约成功",
        "start_time": booking.start_time,
        "participants": len(all_participants),
    }


@router.post("/{booking_id}/complete", summary="完成会议")
async def complete_meeting(
    booking_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    result = await db.execute(
        select(MeetingBooking).where(MeetingBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "会议不存在")
    if booking.organizer_id != me.id:
        raise HTTPException(403, "只有组织者可以结束会议")
    if booking.status == "completed":
        raise HTTPException(400, "会议已结束")

    booking.status = "completed"

    # 给所有参与者奖励XP
    participants = booking.participant_ids or []
    rewarded = []
    for pid in participants:
        p_result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == pid)
        )
        profile = p_result.scalar_one_or_none()
        if profile:
            profile.xp += booking.xp_reward
            rewarded.append(profile.nickname)
            await extract_memory(
                db, pid, "task_complete",
                f"参加会议「{booking.title}」，获得{booking.xp_reward}XP",
            )

    await db.flush()

    return {
        "message": "会议已完成",
        "xp_reward": booking.xp_reward,
        "participants_rewarded": len(rewarded),
    }


@router.post("/{booking_id}/cancel", summary="取消会议")
async def cancel_meeting(
    booking_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    result = await db.execute(
        select(MeetingBooking).where(MeetingBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "会议不存在")
    if booking.organizer_id != me.id:
        raise HTTPException(403, "只有组织者可以取消会议")
    if booking.status in ("completed", "cancelled"):
        raise HTTPException(400, "会议已结束或已取消")

    booking.status = "cancelled"
    await db.flush()

    return {"message": "会议已取消"}
