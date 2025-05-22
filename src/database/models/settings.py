from sqlalchemy import Column, Integer, String, Boolean, JSON
from .base import Base

class Settings(Base):
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(JSON)
    is_active = Column(Boolean, default=True)
    description = Column(String(1024)) 