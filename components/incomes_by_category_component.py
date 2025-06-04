import streamlit as st
import requests
import plotly.express as px
import pandas as pd
from settings import BACKEND_URL
from datetime import date
from typing import Optional

def generate_incomes_pie_chart(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
):
    """
    Generates and displays a pie chart of incomes by category.
    """
    params = {}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if account_id:
        params["account_id"] = account_id

    try:
        response = requests.get(f"{BACKEND_URL}/dashboard/incomes_by_category", params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            st.info("Não há dados de receitas por categoria para o período ou filtros selecionados.")
            return

        df = pd.DataFrame(data)
        if 'category' not in df.columns or 'total_amount' not in df.columns:
            st.warning("Dados de receitas recebidos em formato inesperado.")
            return
            
        fig = px.pie(df, names='category', values='total_amount', title="Receitas por Categoria")
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True, key="incomes_pie_chart")

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar dados de receitas por categoria: {e}")
    except Exception as e:
        st.error(f"Erro ao processar dados do gráfico de receitas por categoria: {e}")