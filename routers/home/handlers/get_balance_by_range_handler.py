from settings import get_session
from sqlalchemy.future import select
from postgres.data_models.balance import Balance
from settings import logger
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

async def execute(time_range: str):
    session = await get_session()
    try:
        # Pegar a data atual e remover a hora
        today = datetime.today().date()

        # Determinar a data limite com base no time_range
        if time_range == "week":
            start_date = today - timedelta(weeks=1)
            interval = timedelta(days=1)
        elif time_range == "month":
            start_date = today - relativedelta(months=1)
            interval = timedelta(days=1)
        elif time_range == "year":
            start_date = today - relativedelta(years=1)
            interval = relativedelta(months=1)  # Saldos mensais
        elif time_range == "all":
            start_date = None  # Não aplicamos filtro de data
            interval = timedelta(days=1)  # Ou qualquer intervalo, pois pega todos os registros
        else:
            logger.error(f"Invalid time_range: {time_range}")
            return {}

        # Calculando o saldo acumulado até start_date
        if start_date:
            initial_balance_query = select(func.sum(Balance.value)).where(Balance.date < start_date)
            initial_result = await session.execute(initial_balance_query)
            initial_balance = initial_result.scalar() or 0  # Caso não haja valores, inicializa em 0
        else:
            initial_balance = 0

        # Consulta para obter o saldo diário/mensal a partir de start_date
        query = (
            select(
                func.DATE(Balance.date).label('date'),  # Garante que a data seja apenas ano-mês-dia
                Balance.value,
                (initial_balance + func.sum(Balance.value).over(order_by=Balance.date)).label("accumulated_balance")
            )
            .where(Balance.date >= start_date if start_date else True)
            .order_by(Balance.date)
        )

        # Executando a consulta
        result = await session.execute(query)

        # Processando o resultado para criar o histórico acumulado
        balance_history = {}
        current_date = start_date if start_date else today
        accumulated_balance = initial_balance

        for row in result:
            # Avançar até a data da transação
            while current_date < row.date:
                balance_history[current_date] = accumulated_balance
                current_date += interval

            # Atualizar o saldo acumulado com o valor da transação
            accumulated_balance = row.accumulated_balance
            balance_history[row.date] = accumulated_balance
            current_date += interval

        # Preencher saldo acumulado até hoje caso faltem dias no intervalo solicitado
        while current_date <= today:
            balance_history[current_date] = accumulated_balance
            current_date += interval

        # Converte todas as datas no dicionário `balance_history` para apenas ano, mês e dia
        balance_history = {date.isoformat(): value for date, value in balance_history.items()}

        return balance_history

    except Exception as e:
        logger.error(e)
        return {}
