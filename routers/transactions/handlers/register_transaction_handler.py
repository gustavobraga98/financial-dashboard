from postgres.data_models.balance import Balance
from routers.transactions.data_models.new_transaction_registered_data_model import NewTransactionRegisteredDataModel
from settings import get_session
from datetime import datetime, timezone

async def execute(transaction):
    try:
        session = await get_session()
        if transaction.type == "outcome":
            transaction.value *= -1
        new_transaction = Balance(
            type=transaction.type,
            value=transaction.value,
            description=transaction.description,
            category=transaction.category,
            date=transaction.date or datetime.now(timezone.utc).date()  # Use a data fornecida ou a data atual se não houver
        )
        session.add(new_transaction)
        await session.commit()
        await session.refresh(new_transaction)
        return NewTransactionRegisteredDataModel(sucess=True,
                                                 message="Transação registrada com sucesso!")
    except Exception as e:
        return NewTransactionRegisteredDataModel(sucess=False,
                                                 message=f"Erro ao registrar transação: {e}")

    