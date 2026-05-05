from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Credit(Base):
    __tablename__ = "credits"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, index=True)
    amount = Column(Float)
    type = Column(String) # 'expense' or 'income' (payment)
    category = Column(String, index=True, nullable=True)
    date = Column(DateTime(timezone=True))
    card_alias = Column(String, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
