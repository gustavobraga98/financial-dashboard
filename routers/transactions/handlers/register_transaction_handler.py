from postgres.data_models import Transaction, Balance, Categories
from routers.transactions.data_models.new_transaction_registered_data_model import NewTransactionRegisteredDataModel
from settings import get_session
from datetime import datetime, timezone
from sqlalchemy import select, func

async def execute(transaction):
    try:
        session = await get_session()

        # Verifique se o tipo da transação é "outcome" e inverta o valor
        if transaction.type == "outcome":
            transaction.value *= -1

        # Passo 1: Buscar a categoria correspondente ao nome fornecido
        category = await session.execute(
            select(Categories).where(func.lower(Categories.name) == func.lower(transaction.category))
        )
        category = category.scalar()

        if not category:
            # Se a categoria não existir, crie uma nova
            new_category = Categories(name=transaction.category)
            session.add(new_category)
            await session.commit()
            await session.refresh(new_category)
            category = new_category

        # Passo 2: Criação da nova transação com a categoria correta
        new_transaction = Transaction(
            type=transaction.type,
            value=transaction.value,
            description=transaction.description,
            category=category,  # Atribuindo a instância de categoria
            date=transaction.date or datetime.now(timezone.utc).date()  # Use a data fornecida ou a data atual
        )

        # Adicione a transação ao banco de dados
        session.add(new_transaction)
        await session.commit()

        # Passo 3: Agora, atualize o Balance com o novo valor da transação
        # Busque o saldo mais recente para a mesma data da transação
        existing_balance = await session.execute(
            select(Balance).where(Balance.date == transaction.date).order_by(Balance.date.desc())
        )
        existing_balance = existing_balance.scalar()

        if existing_balance:
            # Se já existir um saldo, atualize seu valor
            new_balance_value = existing_balance.value + transaction.value
            existing_balance.value = new_balance_value
            session.add(existing_balance)
        else:
            # Se não existir um saldo para essa data, crie uma nova entrada
            new_balance = Balance(
                date=transaction.date,
                value=transaction.value
            )
            session.add(new_balance)

        # Passo 4: Atualizar os saldos dos dias subsequentes
        # Encontre os saldos a partir do dia seguinte à data da transação
        future_balances = await session.execute(
            select(Balance).where(Balance.date > transaction.date).order_by(Balance.date.asc())
        )
        future_balances = future_balances.scalars().all()

        # Se existirem saldos futuros, ajuste-os com base no saldo mais recente
        if future_balances:
            for balance in future_balances:
                balance.value += transaction.value
                session.add(balance)

        # Commit para salvar as mudanças no banco
        await session.commit()

        # Retorne a resposta de sucesso
        return NewTransactionRegisteredDataModel(sucess=True,
                                                 message="Transação registrada com sucesso!")

    except Exception as e:
        return NewTransactionRegisteredDataModel(sucess=False,
                                                 message=f"Erro ao registrar transação: {e}")
