from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models import Transaction
from services.db.session import get_db
from typing import Optional, List, Dict
from datetime import date

def execute(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
) -> List[Dict[str, any]]:
    query = (
        db.query(
            Transaction.date,
            Transaction.balance
        )
        .order_by(Transaction.date.asc(), Transaction.created_at.asc())
    )

    # Subquery to get the last transaction for each day
    # This is important if there are multiple transactions with balances on the same day,
    # we want the final balance of that day.
    # Or, if balances are cumulative and always correct per transaction,
    # we might want the balance of the last transaction of the day.
    # For simplicity, let's get distinct dates and their latest balance.

    # A more precise way if `balance` is the balance *after* the transaction:
    # We need the balance of the last transaction of each day.
    sub_query = (
        db.query(
            Transaction.date,
            func.max(Transaction.created_at).label("max_created_at")
        )
        .group_by(Transaction.date).subquery()
    )

    query = (
        db.query(Transaction.date, Transaction.balance)
        .join(
            sub_query,
            (Transaction.date == sub_query.c.date) &
            (Transaction.created_at == sub_query.c.max_created_at)
        )
    )

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    query = query.order_by(Transaction.date.asc())

    results = query.all()
    return [{"date": r.date.isoformat(), "balance": float(r.balance)} for r in results]