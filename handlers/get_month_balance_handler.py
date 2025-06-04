from services.db.session import get_db
from models import Transaction
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import Session
from datetime import timedelta
from sqlalchemy import func

def execute():
    db: Session = next(get_db())
    thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
    results = db.query(Transaction.type, func.sum(Transaction.amount)).filter(Transaction.date >= thirty_days_ago).group_by(Transaction.type).all()
    
    total_incomes = 0
    total_outcomes = 0
    
    for transaction_type, total in results:
        if transaction_type == 'income':
            total_incomes = total
        elif transaction_type == 'outcome':
            total_outcomes = total
    
    return {"income": total_incomes, "outcome": -total_outcomes} # Just so we get positive values as it is already labeled as outcome