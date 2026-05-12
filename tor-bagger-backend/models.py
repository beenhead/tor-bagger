# models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # Relationship to the logbook
    logs = relationship("Logbook", back_populates="user")


class Tor(Base):
    __tablename__ = "tors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    elevation_m = Column(Integer, nullable=True)

    # Relationship to the logbook
    logs = relationship("Logbook", back_populates="tor")


class Logbook(Base):
    __tablename__ = "logbook"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tor_id = Column(Integer, ForeignKey("tors.id"), nullable=False)
    bagged_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # How close did they get? (Useful for our near-miss logic later)
    distance_meters = Column(Float, nullable=True) 

    # Relationships back to the user and tor
    user = relationship("User", back_populates="logs")
    tor = relationship("Tor", back_populates="logs")