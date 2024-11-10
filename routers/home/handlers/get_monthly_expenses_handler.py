from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from postgres.data_models.transaction import Transaction
from settings import get_session
from sqlalchemy import func, select

async def execute():
    session = await get_session()
    today = datetime.today().date()
    month_start = today - relativedelta(months=1)

    # Consultas para receitas e despesas com base nas transações do último mês
    total_income_query = select(func.sum(Transaction.value)).where(
        Transaction.date >= month_start,
        Transaction.type == "income"
    )
    total_expenses_query = select(func.sum(Transaction.value)).where(
        Transaction.date >= month_start,
        Transaction.type == "outcome"
    )

    # Executando as consultas
    total_income = await session.execute(total_income_query)
    total_expenses = await session.execute(total_expenses_query)

    total_income = total_income.scalar_one_or_none() or 0
    total_expenses = total_expenses.scalar_one_or_none() or 0

    # Se o total de despesas for negativo, ajustamos para o valor positivo representando a saída
    total_expenses = abs(total_expenses)

    if total_expenses > total_income:
        total_percentage = 0
    else:

        # Calculando a porcentagem de despesas em relação à receita
        total_percentage = (total_expenses / total_income) if total_income != 0 else 0

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_percentage": total_percentage
    }
