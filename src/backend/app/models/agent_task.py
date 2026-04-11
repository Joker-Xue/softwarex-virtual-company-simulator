"""
AgentTaskModel
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentTask(Base):
    """Virtual RoleTask table"""
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), default="daily")  # daily/project/special
    difficulty = Column(Integer, default=1)  # 1-5
    xp_reward = Column(Integer, default=20)
    assigner_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True)
    assignee_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending/in_progress/completed/expired
    deadline = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
