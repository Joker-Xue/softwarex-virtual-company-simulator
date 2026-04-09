"""
金币商店模型 - 钱包、商品、交易记录
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CoinWallet(Base):
    """金币钱包表"""
    __tablename__ = "coin_wallets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    balance = Column(Integer, default=0)  # 当前余额
    total_earned = Column(Integer, default=0)  # 累计获得
    total_spent = Column(Integer, default=0)  # 累计消费
    last_checkin_date = Column(Date, nullable=True)  # 最后签到日期
    checkin_streak = Column(Integer, default=0)  # 连续签到天数
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="coin_wallet")

    def __repr__(self):
        return f"<CoinWallet(user_id={self.user_id}, balance={self.balance})>"


class ShopItem(Base):
    """商品表"""
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)  # 金币价格
    icon = Column(String(50), nullable=True)  # 图标标识
    category = Column(String(50), nullable=True)  # 分类
    is_active = Column(Boolean, default=True)  # 是否上架
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ShopItem(id={self.id}, name={self.name}, price={self.price})>"


class CoinTransaction(Base):
    """金币交易记录表"""
    __tablename__ = "coin_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # 金额（正数=收入，负数=支出）
    type = Column(String(10), nullable=False)  # earn / spend
    source = Column(String(50), nullable=False)  # 来源：checkin, game, purchase, etc.
    description = Column(String(255), nullable=True)
    item_id = Column(Integer, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="coin_transactions")
    item = relationship("ShopItem", backref="transactions")

    def __repr__(self):
        return f"<CoinTransaction(user_id={self.user_id}, amount={self.amount}, type={self.type})>"
