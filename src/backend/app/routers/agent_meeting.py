"""
Meeting Room Reservation System API
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
        raise HTTPException(404, "Profile has not been created yet")
    return profile


# ── Endpoints ──

@router.get("/list", summary="Meeting reservation list")
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

    # Rich display of data
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


@router.post("/create", summary="Book a Meeting Room")
async def create_meeting(
    body: MeetingCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # Verify that the room exists and is Meeting Room
    room_result = await db.execute(
        select(CompanyRoom).where(CompanyRoom.id == body.room_id)
    )
    room = room_result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room does not exist")
    if room.room_type not in ("meeting", "office", "ceo_office"):
        raise HTTPException(400, "This room does not support meeting reservations")

    # Verify that time is not in the past
    if body.start_time < datetime.now(timezone.utc):
        raise HTTPException(400, "Meeting start time cannot be in the past")

    # Verify that there is no time conflict
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
            raise HTTPException(409, f'Conflicts with the existing meeting "{c.title}"')

    # Verify participant exists
    all_participants = list(set([me.id] + body.participant_ids))
    if len(all_participants) > room.capacity:
        raise HTTPException(400, f"Participating in Headcount exceeds room capacity({room.capacity})")

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

    # Memories
    await extract_memory(
        db, me.id, "task_complete",
        f'Scheduled meeting "{body.title}" and invited {len(all_participants) - 1} colleagues',
    )

    return {
        "id": booking.id,
        "message": "Meeting reservation successful",
        "start_time": booking.start_time,
        "participants": len(all_participants),
    }


@router.post("/{booking_id}/complete", summary="Complete meeting")
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
        raise HTTPException(404, "The meeting does not exist")
    if booking.organizer_id != me.id:
        raise HTTPException(403, "Only the organizer can end the meeting")
    if booking.status == "completed":
        raise HTTPException(400, "Meeting has ended")

    booking.status = "completed"

    # Give rewardXP to all participants
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
                f"join meeting「{booking.title}」，gain{booking.xp_reward}XP",
            )

    await db.flush()

    return {
        "message": "MeetingCompleted",
        "xp_reward": booking.xp_reward,
        "participants_rewarded": len(rewarded),
    }


@router.post("/{booking_id}/cancel", summary="Cancel Meeting")
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
        raise HTTPException(404, "The meeting does not exist")
    if booking.organizer_id != me.id:
        raise HTTPException(403, "Only the organizer can cancel a meeting")
    if booking.status in ("completed", "cancelled"):
        raise HTTPException(400, "Meeting has ended or been canceled")

    booking.status = "cancelled"
    await db.flush()

    return {"message": "Meeting canceled"}
