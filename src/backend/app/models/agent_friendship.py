"""
Agent好友关系模型
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class AgentFriendship(Base):
    """好友关系表"""
    __tablename__ = "agent_friendships"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    from_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    to_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending/accepted/rejected
    affinity = Column(Integer, default=50)  # 好感度 0-100
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    last_interaction_at = Column(DateTime(timezone=True), nullable=True)  # 最后互动时间

    __table_args__ = (UniqueConstraint("from_id", "to_id", name="uq_friendship"),)
