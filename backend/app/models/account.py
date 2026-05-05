from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    initial_balance = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
