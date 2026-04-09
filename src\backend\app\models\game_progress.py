"""
闯关进度模型
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class GameProgress(Base):
    """闯关进度表"""
    __tablename__ = "game_progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    current_level = Column(Integer, default=1)  # 当前关卡
    completed_levels = Column(JSON, default=list)  # 已完成关卡ID列表
    total_coins_earned = Column(Integer, default=0)  # 通过闯关获得的总金币
    completion_streak = Column(Integer, default=0)  # 连续完成关卡天数
    last_completion_date = Column(String(10), nullable=True)  # "YYYY-MM-DD"
    longest_streak = Column(Integer, default=0)  # 历史最长连续天数
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联关系
    user = relationship("User", backref="game_progress")

    def __repr__(self):
        return f"<GameProgress(user_id={self.user_id}, current_level={self.current_level})>"
