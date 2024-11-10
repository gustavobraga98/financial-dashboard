from postgres.data_models.general_base import Base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

class Categories(Base):
    __tablename__ = 'Categories'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    # Relacionamento reverso com Balance
    balances = relationship("Balance", back_populates="category")
