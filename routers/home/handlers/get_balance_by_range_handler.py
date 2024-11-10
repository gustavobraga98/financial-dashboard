from settings import get_session
from sqlalchemy.future import select
from postgres.data_models.balance import Balance
from settings import logger
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

async def execute(time_range: str):
    session = await get_session()
    try:
        # Pegar a data atual e remover a hora (só fica o ano, mês e dia)
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
            interval = relativedelta(months=1)  # Para saldo mensal
        elif time_range == "all":
            start_date = None  # Não aplicamos filtro de data
            interval = timedelta(days=1)  # Ou qualquer intervalo, pois pega todos os registros
        else:
            logger.error(f"Invalid time_range: {time_range}")
            return {}

        # Consulta para obter os saldos dentro do intervalo de tempo especificado
        query = select(Balance).where(Balance.date >= start_date if start_date else True).order_by(Balance.date)

        # Executando a consulta
        result = await session.execute(query)

        # Processando o resultado (usando scalars() para obter uma lista de objetos Balance)
        balance_history = {}
        balances = result.scalars().all()  # Obtém todos os registros de saldo como objetos

        # Iterando sobre os saldos e preenchendo o histórico
        for row in balances:
            balance_history[row.date] = row.value

        # Se necessário, preenche os dias faltantes até hoje
        current_date = start_date if start_date else today
        while current_date <= today:
            if current_date not in balance_history:
                balance_history[current_date] = 0  # Se não houver saldo, considera como 0
            current_date += interval

        # Converte todas as datas no dicionário `balance_history` para apenas ano, mês e dia
        balance_history = {date.isoformat(): value for date, value in balance_history.items()}

        return balance_history

    except Exception as e:
        logger.error(e)
        return {}
