"""
Agent薪资记录模型
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AgentSalaryLog(Base):
    """薪资发放记录表"""
    __tablename__ = "agent_salary_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    salary_type = Column(String(30), default="daily")  # daily/bonus/performance
    description = Column(String(200), nullable=True)
    paid_at = Column(DateTime(timezone=True), server_default=func.now())
