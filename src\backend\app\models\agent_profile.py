"""
虚拟Agent角色档案模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class AgentProfile(Base):
    """虚拟角色档案表"""
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    nickname = Column(String(50), nullable=False)
    avatar_key = Column(String(50), default="default")
    mbti = Column(String(4), nullable=False)
    personality = Column(JSON, default=list)
    attr_communication = Column(Integer, default=50)
    attr_leadership = Column(Integer, default=50)
    attr_creativity = Column(Integer, default=50)
    attr_technical = Column(Integer, default=50)
    attr_teamwork = Column(Integer, default=50)
    attr_diligence = Column(Integer, default=50)
    career_level = Column(Integer, default=0)
    career_path = Column(String(20), default="")  # "" 未选择, "management" 管理, "technical" 技术
    department = Column(String(50), default="unassigned")
    tasks_completed = Column(Integer, default=0)
    xp = Column(Integer, default=0)
    pos_x = Column(Integer, default=400)
    pos_y = Column(Integer, default=300)
    current_action = Column(String(50), default="idle")
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    ai_enabled = Column(Boolean, default=True)
    daily_schedule = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="agent_profile")
