"""
公司社交活动模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class CompanyEvent(Base):
    """公司活动表"""
    __tablename__ = "company_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    event_type = Column(String(30), nullable=False)  # tea_break/team_building/birthday/holiday
    description = Column(Text, nullable=True)
    room_id = Column(Integer, ForeignKey("company_rooms.id", ondelete="SET NULL"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=60)
    max_participants = Column(Integer, default=20)
    participants = Column(JSON, default=list)  # [agent_id, ...]
    rewards_xp = Column(Integer, default=20)
    rewards_coins = Column(Integer, default=10)
    is_active = Column(String(10), default="upcoming")  # upcoming/ongoing/finished
    created_at = Column(DateTime(timezone=True), server_default=func.now())
