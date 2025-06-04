from services.db.session import get_db
from models.transaction import Transaction

def execute():
    db = next(get_db())
    last_transaction = (
        db.query(Transaction)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .first()
    )
    return last_transaction.balance if last_transaction else 0.0
