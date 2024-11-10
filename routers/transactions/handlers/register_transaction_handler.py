from postgres.data_models import Transaction, Balance, Categories
from routers.transactions.data_models.new_transaction_registered_data_model import NewTransactionRegisteredDataModel
from settings import get_session
from datetime import datetime, timezone
from sqlalchemy import select, func

async def execute(transaction):
    try:
        session = await get_session()

        # Ajusta o valor se a transação for um outcome
        if transaction.type == "outcome":
            transaction.value *= -1

        # Passo 1: Buscar a categoria correspondente ao nome fornecido
        category = await session.execute(
            select(Categories).where(func.lower(Categories.name) == func.lower(transaction.category))
        )
        category = category.scalar()

        if not category:
            # Cria nova categoria se não existir
            new_category = Categories(name=transaction.category)
            session.add(new_category)
            await session.commit()
            await session.refresh(new_category)
            category = new_category

        # Passo 2: Criar a transação
        new_transaction = Transaction(
            type=transaction.type,
            value=transaction.value,
            description=transaction.description,
            category=category,
            date=transaction.date
        )

        session.add(new_transaction)
        await session.commit()

        # Passo 3: Atualizar o Balance
        # Tenta buscar um saldo existente para a data da transação
        existing_balance = await session.execute(
            select(Balance).where(Balance.date == transaction.date).order_by(Balance.date.desc())
        )
        existing_balance = existing_balance.scalar()

        if existing_balance:
            # Atualiza o saldo do dia com a transação
            existing_balance.value += transaction.value
            session.add(existing_balance)
        else:
            # Busca o saldo mais recente antes da data da transação
            latest_balance_before_date = await session.execute(
                select(Balance).where(Balance.date < transaction.date).order_by(Balance.date.desc()).limit(1)
            )
            latest_balance = latest_balance_before_date.scalar()
            latest_balance_value = latest_balance.value if latest_balance else 0

            # Cria nova entrada no Balance somando o valor mais recente com o valor da transação
            new_balance = Balance(
                date=transaction.date,
                value=latest_balance_value + transaction.value
            )
            session.add(new_balance)

        # Passo 4: Ajusta saldos dos dias futuros
        future_balances = await session.execute(
            select(Balance).where(Balance.date > transaction.date).order_by(Balance.date.asc())
        )
        future_balances = future_balances.scalars().all()

        if future_balances:
            for balance in future_balances:
                balance.value += transaction.value
                session.add(balance)

        await session.commit()

        return NewTransactionRegisteredDataModel(sucess=True,
                                                 message="Transação registrada com sucesso!")

    except Exception as e:
        return NewTransactionRegisteredDataModel(sucess=False,
                                                 message=f"Erro ao registrar transação: {e}")
