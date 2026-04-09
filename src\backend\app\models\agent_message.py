"""
Agent私聊消息模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentMessage(Base):
    """私聊消息表"""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(Integer, nullable=True, index=True)  # NULL=群聊广播，非NULL=私聊
    content = Column(Text, nullable=False)
    msg_type = Column(String(20), default="text")  # text/system/ai_generated
    group_id = Column(String(50), nullable=True, index=True)  # NULL=私聊, 非NULL=群聊频道ID
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
