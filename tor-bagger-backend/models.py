# models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    is_admin = Column(Boolean, default=False)
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
    description = Column(Text, nullable=True)

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

class TorSuggestion(Base):
    __tablename__ = "tor_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    tor_id = Column(Integer, ForeignKey("tors.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    suggested_name = Column(String(100))
    suggested_lat = Column(Float)
    suggested_lon = Column(Float)
    suggested_elevation = Column(Integer)
    # ADD THIS LINE:
    suggested_description = Column(Text, nullable=True) 
    
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TorReview(Base):
    __tablename__ = "tor_reviews"

    id = Column(Integer, primary_key=True, index=True)
    tor_id = Column(Integer, ForeignKey("tors.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer) # 1 to 5 stars
    comment = Column(String(500))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User")
    tor = relationship("Tor")