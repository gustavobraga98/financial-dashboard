from sqlalchemy.orm import Session # Add Session import
from models import Transaction
from datetime import datetime, timedelta # Keep existing datetime and timedelta imports
from sqlalchemy import func
# Remove: from services.db.session import get_db # No longer needed here

def execute(db: Session): # Modify to accept db session
    thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
    results = db.query(Transaction.type, func.sum(Transaction.amount)).filter(Transaction.date >= thirty_days_ago).group_by(Transaction.type).all()
    
    total_incomes = 0
    total_outcomes = 0
    
    for transaction_type, total in results:
        if transaction_type == 'income':
            total_incomes = total
        elif transaction_type == 'outcome':
            total_outcomes = total
    
    return {"income": total_incomes, "outcome": -total_outcomes}