from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta  # Corrigido para importar de dateutil
from postgres.data_models.balance import Balance
from settings import get_session
from sqlalchemy import func, select


async def execute():
    session = await get_session()
    today = datetime.today().date()
    month_start = today - relativedelta(months=1)

    total_income_query = select(func.sum(Balance.value)).where(Balance.date >= month_start, Balance.type == "income")
    total_expenses_query = select(func.sum(Balance.value)).where(Balance.date >= month_start, Balance.type == "outcome")

    total_income = await session.execute(total_income_query)
    total_expenses = await session.execute(total_expenses_query)

    total_income = total_income.scalar_one_or_none() or 0
    total_expenses = total_expenses.scalar_one_or_none() or 0

    total_expenses = total_expenses * -1

    total_percentage = (total_expenses / total_income) if total_income != 0 else 0

    return {"total_income": total_income, "total_expenses": total_expenses, "total_percentage": total_percentage}
