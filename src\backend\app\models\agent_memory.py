"""
Agent长期记忆模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentMemory(Base):
    """Agent记忆表"""
    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    memory_type = Column(String(30), default="observation")  # interaction/task/observation/promotion
    importance = Column(Integer, default=3)  # 1-10
    related_agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
