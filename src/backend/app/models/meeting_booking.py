"""
Meeting Room reservation model
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class MeetingBooking(Base):
    """Meeting Room reservation form"""
    __tablename__ = "meeting_bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("company_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    organizer_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), default="")
    start_time = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=60)  # 30/60/90
    participant_ids = Column(JSON, default=list)  # Agent ID list
    status = Column(String(20), default="scheduled")  # scheduled/in_progress/completed/cancelled
    xp_reward = Column(Integer, default=20)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
