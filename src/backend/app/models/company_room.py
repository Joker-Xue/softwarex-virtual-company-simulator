"""
公司房间模型
"""
from sqlalchemy import Column, Integer, String, JSON
from app.database import Base


class CompanyRoom(Base):
    """公司房间表"""
    __tablename__ = "company_rooms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    room_type = Column(String(50), nullable=False)  # office/meeting/cafeteria/lounge/ceo_office
    department = Column(String(50), default="general")
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    capacity = Column(Integer, default=10)
    floor = Column(Integer, default=1)  # 楼层编号
    interior_objects = Column(JSON, default=list)  # 内部物件列表
    description = Column(String(200), nullable=True)
