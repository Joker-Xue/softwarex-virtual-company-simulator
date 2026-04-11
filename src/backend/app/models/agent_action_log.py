"""
AgentBehaviorLogModel
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentActionLog(Base):
    """Behavior log table"""
    __tablename__ = "agent_action_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # move/work/chat/rest/meeting
    detail = Column(JSON, default=dict)
    location = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
