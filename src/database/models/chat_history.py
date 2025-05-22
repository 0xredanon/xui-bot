from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class ChatHistory(Base):
    __tablename__ = 'chat_history'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_type = Column(String(64), nullable=True)
    message_text = Column(String(4096), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String(4096), nullable=True)  # for backward compatibility
    response = Column(String(4096), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_history") 