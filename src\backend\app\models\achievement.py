"""
成就系统模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class Achievement(Base):
    """成就定义表"""
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)  # unique identifier e.g. "first_task"
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(30))  # task/social/career/economy/explore
    icon = Column(String(50), default="🏆")
    coin_reward = Column(Integer, default=50)
    condition_type = Column(String(50))  # tasks_completed/friends_count/career_level/coins_earned/rooms_visited/streak_days
    condition_value = Column(Integer, default=1)
    is_hidden = Column(Boolean, default=False)  # hidden achievements
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserAchievement(Base):
    """用户成就记录表"""
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("agent_id", "achievement_id", name="uq_user_achievement"),)
