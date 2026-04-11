"""
AgentDirectinformationModel
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentMessage(Base):
    """Directinformation"""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(Integer, nullable=True, index=True)  # NULL=group chat broadcast，non-NULL=Direct
    content = Column(Text, nullable=False)
    msg_type = Column(String(20), default="text")  # text/system/ai_generated
    group_id = Column(String(50), nullable=True, index=True)  # NULL=Direct, non-NULL=Group chatChannelsID
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
