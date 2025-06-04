from pydantic import BaseModel
from pandas import DataFrame
from models import Transaction
from services.db.session import get_db
from datetime import datetime, date
from decimal import Decimal

class RegisterDFModel(BaseModel):
    df: DataFrame
    account_id: int

    model_config = {
        "arbitrary_types_allowed": True
    }

def execute(payload: RegisterDFModel):
    db = next(get_db())
    last_transaction = (
        db.query(Transaction)
        .filter(Transaction.account_id == payload.account_id)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .first()
    )

    for row in payload.df.itertuples(index=False):
        date_obj = datetime.strptime(row.date, "%d/%m/%Y").date()  # Converte para date
        formatted_date = date_obj.strftime("%Y-%m-%d")

        # Se a data da transação está no futuro, pula (continue)
        if date_obj > date.today():
            continue

        # Verifica se já existe transação igual
        existing = db.query(Transaction).filter_by(
            account_id=payload.account_id,
            date=formatted_date,
            description=row.description,
            amount=row.amount
        ).first()

        if existing:
            continue  # Pula para a próxima

        transaction = Transaction(
            account_id=payload.account_id,
            date=formatted_date,
            description=row.description,
            amount=Decimal(row.amount),
            type="input" if row.amount > 0 else "output",
            category=None,
            balance=(
                last_transaction.balance + Decimal(row.amount)
                if last_transaction
                else Decimal(row.amount)
            ),
        )
        last_transaction = transaction
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
