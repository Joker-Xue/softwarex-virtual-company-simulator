"""
Passage progress model
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class GameProgress(Base):
    """Level progress chart"""
    __tablename__ = "game_progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    current_level = Column(Integer, default=1)  # Current level
    completed_levels = Column(JSON, default=list)  # Completed level ID list
    total_coins_earned = Column(Integer, default=0)  # Total gold coins gained by passing levels
    completion_streak = Column(Integer, default=0)  # Number of consecutive days to complete levels
    last_completion_date = Column(String(10), nullable=True)  # "YYYY-MM-DD"
    longest_streak = Column(Integer, default=0)  # The longest consecutive days in history
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Association relationship
    user = relationship("User", backref="game_progress")

    def __repr__(self):
        return f"<GameProgress(user_id={self.user_id}, current_level={self.current_level})>"
