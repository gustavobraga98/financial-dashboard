import streamlit as st
import requests
import pandas as pd
from settings import BACKEND_URL
from datetime import date
from typing import Optional, List

def display_transactions_table(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    transaction_type: Optional[str] = None,
    category: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: int = 20,
    page: int = 1 # Page number, 1-indexed
):
    """
    Displays a table of transactions with optional filters and pagination.
    """
    offset = (page - 1) * limit
    params = {"limit": limit, "offset": offset}

    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if transaction_type:
        params["transaction_type"] = transaction_type
    if category:
        params["category"] = category
    if account_id:
        params["account_id"] = account_id

    try:
        response = requests.get(f"{BACKEND_URL}/dashboard/transactions", params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            st.info("Nenhuma transação encontrada para os filtros selecionados.")
            return pd.DataFrame() # Return empty DataFrame for consistency

        df = pd.DataFrame(data)
        # Format columns for display
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%d/%m/%Y')
        df['amount'] = df['amount'].apply(lambda x: f"R$ {x:_.2f}".replace('.', ',').replace('_', '.'))
        df['balance'] = df['balance'].apply(lambda x: f"R$ {x:_.2f}".replace('.', ',').replace('_', '.') if pd.notnull(x) else 'N/A')
        df.rename(columns={
            'date': 'Data', 'description': 'Descrição', 'amount': 'Valor',
            'type': 'Tipo', 'category': 'Categoria', 'balance': 'Saldo Após',
            'account_id': 'ID Conta'
        }, inplace=True)
        
        # Select and reorder columns for display
        display_columns = ['Data', 'Descrição', 'Valor', 'Tipo', 'Categoria', 'Saldo Após']
        st.dataframe(df[display_columns], use_container_width=True, hide_index=True)
        return df # Return the original df for potential further use (like getting total count for pagination)

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar transações: {e}")
    except Exception as e:
        st.error(f"Erro ao processar dados da tabela de transações: {e}")
    return pd.DataFrame()