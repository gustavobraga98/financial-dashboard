from sqlalchemy.orm import Session
from models import Transaction
from services.db.session import get_db
from typing import Optional, List, Dict, Any
from datetime import date
from decimal import Decimal

def execute(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    transaction_type: Optional[str] = None, # 'income' or 'outcome'
    category: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    query = db.query(Transaction)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)
    if category:
        query = query.filter(Transaction.category.ilike(f"%{category}%")) # Case-insensitive search

    query = query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
    query = query.limit(limit).offset(offset)

    results = query.all()
    
    return [
        {
            "id": r.id,
            "account_id": r.account_id,
            "date": r.date.isoformat(),
            "description": r.description,
            "amount": float(r.amount),
            "type": r.type,
            "category": r.category,
            "balance": float(r.balance) if r.balance is not None else None,
            "created_at": r.created_at.isoformat()
        }
        for r in results
    ]