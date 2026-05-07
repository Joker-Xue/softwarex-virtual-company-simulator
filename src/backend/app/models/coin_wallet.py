"""
Gold Coin Store Model - Wallet, Products, Transaction Records
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CoinWallet(Base):
    """gold coin wallet table"""
    __tablename__ = "coin_wallets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    balance = Column(Integer, default=0)  # CurrentBalance
    total_earned = Column(Integer, default=0)  # Accumulated gain
    total_spent = Column(Integer, default=0)  # Accumulated consumption
    last_checkin_date = Column(Date, nullable=True)  # Last check-in date
    checkin_streak = Column(Integer, default=0)  # Number of consecutive check-in days
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="coin_wallet")

    def __repr__(self):
        return f"<CoinWallet(user_id={self.user_id}, balance={self.balance})>"


class ShopItem(Base):
    """Product list"""
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)  # coins price
    icon = Column(String(50), nullable=True)  # icon logo
    category = Column(String(50), nullable=True)  # Classification
    is_active = Column(Boolean, default=True)  # Is it on the shelves?
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ShopItem(id={self.id}, name={self.name}, price={self.price})>"


class CoinTransaction(Base):
    """Gold coin transaction record table"""
    __tablename__ = "coin_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount（positive number=income，negative number=expenditure）
    type = Column(String(10), nullable=False)  # earn / spend
    source = Column(String(50), nullable=False)  # source：checkin, game, purchase, etc.
    description = Column(String(255), nullable=True)
    item_id = Column(Integer, ForeignKey("shop_items.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="coin_transactions")
    item = relationship("ShopItem", backref="transactions")

    def __repr__(self):
        return f"<CoinTransaction(user_id={self.user_id}, amount={self.amount}, type={self.type})>"
