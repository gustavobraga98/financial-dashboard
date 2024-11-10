from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, func
from postgres.data_models import Transaction
from settings import get_session
from settings import logger
from sqlalchemy import select, func
from postgres.data_models import Transaction, Categories
from settings import get_session

async def execute(type: str, time_range: str):
    session = await get_session()

    # Obter a data atual
    today = datetime.today().date()

    # Configurar a data inicial com base no time_range
    if time_range == "week":
        start_date = today - timedelta(weeks=1)
    elif time_range == "month":
        start_date = today - relativedelta(months=1)
    elif time_range == "year":
        start_date = today - relativedelta(years=1)
    else:
        start_date = None  # Para pegar todas as transações se o time_range for "all" ou não especificado

    # Filtrar e agrupar as transações com base no tipo e no intervalo de tempo
    query = (
        select(Categories.name, Transaction.id, Transaction.value, Transaction.description, Transaction.date)
        .join(Transaction, Transaction.category_id == Categories.id)
        .where(Transaction.type == type)
    )
    if start_date:
        query = query.where(Transaction.date >= start_date)

    # Executa a consulta e organiza os dados
    result = await session.execute(query)
    transactions = result.fetchall()

    # Organizar o resultado em um dicionário com detalhes de cada categoria
    categorized_data = {}
    for category_name, transaction_id, value, description, date in transactions:
        if category_name not in categorized_data:
            categorized_data[category_name] = {
                "total": 0,  # Valor total de gastos por categoria para o gráfico de pizza
                "transactions": []  # Detalhamento de cada transação dentro da categoria
            }

        # Somar o valor absoluto (mudar de negativo para positivo se necessário)
        categorized_data[category_name]["total"] += abs(value)

        # Adicionar detalhes de cada transação
        categorized_data[category_name]["transactions"].append({
            "id": transaction_id,
            "value": value,
            "description": description,
            "date": date.isoformat()
        })

    # Dicionário final, onde cada chave é uma categoria e o valor é um dicionário com o total e a lista de transações
    return categorized_data
