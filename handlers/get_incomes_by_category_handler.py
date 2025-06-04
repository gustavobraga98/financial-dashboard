from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Transaction
from services.db.session import get_db
from typing import Optional, List, Dict
from datetime import date
from decimal import Decimal

def execute(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
) -> List[Dict[str, any]]:
    query = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_amount")
        )
        .filter(Transaction.type == 'income')
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    query = query.group_by(Transaction.category).order_by(func.sum(Transaction.amount).desc())

    results = query.all()
    return [{"category": r.category if r.category else "Uncategorized", "total_amount": float(r.total_amount)} for r in results]