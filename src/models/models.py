from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from .base import Base

class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255))
    last_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    activities = relationship("UserActivity", back_populates="user")
    chats = relationship("ChatHistory", back_populates="user")

class VPNClient(Base):
    __tablename__ = "vpn_clients"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True)
    email = Column(String(255))
    inbound_id = Column(Integer)
    enable = Column(Boolean, default=True)
    total_gb = Column(Integer, default=0)  # 0 means unlimited
    upload = Column(BigInteger, default=0)
    download = Column(BigInteger, default=0)
    expire_time = Column(BigInteger, default=0)  # 0 means never expires
    created_at = Column(DateTime, default=datetime.utcnow)
    last_sync = Column(DateTime, default=datetime.utcnow)
    
    # Additional fields from API
    protocol = Column(String(50))
    port = Column(Integer)
    settings = Column(JSON)  # Store complete settings JSON
    
    # Relationships
    ip_logs = relationship("ClientIPLog", back_populates="client")
    traffic_logs = relationship("TrafficLog", back_populates="client")

class UserActivity(Base):
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("telegram_users.id"))
    activity_type = Column(String(50))  # e.g., "STATUS_CHECK", "RESET_TRAFFIC", etc.
    target_uuid = Column(String(36), nullable=True)  # VPN client UUID if applicable
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("TelegramUser", back_populates="activities")

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("telegram_users.id"))
    message_id = Column(Integer)
    message_type = Column(String(50))  # "TEXT", "COMMAND", etc.
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("TelegramUser", back_populates="chats")

class ClientIPLog(Base):
    __tablename__ = "client_ip_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("vpn_clients.id"))
    ip_address = Column(String(45))  # Support IPv6
    connection_time = Column(DateTime, default=datetime.utcnow)
    disconnection_time = Column(DateTime, nullable=True)
    
    # Relationships
    client = relationship("VPNClient", back_populates="ip_logs")

class TrafficLog(Base):
    __tablename__ = "traffic_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("vpn_clients.id"))
    upload = Column(BigInteger, default=0)
    download = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    client = relationship("VPNClient", back_populates="traffic_logs") 