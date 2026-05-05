from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.db.database import get_db

router = APIRouter()

@router.get("/", response_model=List[schemas.CreditResponse])
def read_credits(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    credits = db.query(models.Credit).offset(skip).limit(limit).all()
    return credits

@router.post("/", response_model=schemas.CreditResponse)
def create_credit(credit: schemas.CreditCreate, db: Session = Depends(get_db)):
    db_credit = models.Credit(**credit.model_dump())
    db.add(db_credit)
    db.commit()
    db.refresh(db_credit)
    return db_credit

@router.get("/{credit_id}", response_model=schemas.CreditResponse)
def read_credit(credit_id: int, db: Session = Depends(get_db)):
    db_credit = db.query(models.Credit).filter(models.Credit.id == credit_id).first()
    if db_credit is None:
        raise HTTPException(status_code=404, detail="Credit not found")
    return db_credit

@router.put("/{credit_id}", response_model=schemas.CreditResponse)
def update_credit(credit_id: int, credit: schemas.CreditCreate, db: Session = Depends(get_db)):
    db_credit = db.query(models.Credit).filter(models.Credit.id == credit_id).first()
    if db_credit is None:
        raise HTTPException(status_code=404, detail="Credit not found")
    
    for key, value in credit.model_dump().items():
        setattr(db_credit, key, value)
        
    db.commit()
    db.refresh(db_credit)
    return db_credit

@router.delete("/{credit_id}")
def delete_credit(credit_id: int, db: Session = Depends(get_db)):
    db_credit = db.query(models.Credit).filter(models.Credit.id == credit_id).first()
    if db_credit is None:
        raise HTTPException(status_code=404, detail="Credit not found")
    
    db.delete(db_credit)
    db.commit()
    return {"ok": True}
