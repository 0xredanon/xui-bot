from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from .base import Base

class Admin(Base):
    __tablename__ = 'admins'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    is_super_admin = Column(Boolean, default=False)
    can_manage_users = Column(Boolean, default=False)
    can_manage_settings = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 