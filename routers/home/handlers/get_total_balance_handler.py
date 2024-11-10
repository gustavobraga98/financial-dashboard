from postgres.data_models.balance import Balance
from settings import get_session
from sqlalchemy import select
from sqlalchemy.orm import aliased

async def execute():
    session = await get_session()
    # Seleciona o valor do saldo mais recente
    latest_balance_query = (
        select(Balance.value)
        .order_by(Balance.date.desc())
        .limit(1)
    )
    result = await session.execute(latest_balance_query)
    latest_balance = result.scalar()  # Obtém o valor diretamente

    return {"latest_balance": latest_balance}
