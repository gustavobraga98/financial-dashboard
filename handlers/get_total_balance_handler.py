from sqlalchemy.orm import Session # Add Session import
from models.transaction import Transaction
# Remove: from services.db.session import get_db # No longer needed here

def execute(db: Session): # Modify to accept db session
    last_transaction = (
        db.query(Transaction)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .first()
    )
    return last_transaction.balance if last_transaction else 0.0