import streamlit as st
import requests
import plotly.graph_objects as go
import pandas as pd
from settings import BACKEND_URL
from typing import Optional

def generate_monthly_comparison_bar_chart(
    year: Optional[int] = None,
    account_id: Optional[int] = None
):
    """
    Generates and displays a bar chart comparing monthly income and outcome.
    """
    params = {}
    if year:
        params["year"] = year
    if account_id:
        params["account_id"] = account_id

    try:
        response = requests.get(f"{BACKEND_URL}/dashboard/monthly_comparison", params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            st.info("Não há dados de comparação mensal para o período ou filtros selecionados.")
            return

        df = pd.DataFrame(data)
        if not all(col in df.columns for col in ['month', 'income', 'outcome']):
            st.warning("Dados de comparação mensal recebidos em formato inesperado.")
            return

        fig = go.Figure(data=[
            go.Bar(name='Receitas', x=df['month'], y=df['income'], marker_color='#28a745'),
            go.Bar(name='Despesas', x=df['month'], y=df['outcome'], marker_color='#dc3545')
        ])
        fig.update_layout(
            barmode='group',
            title_text=f"Comparativo Mensal: Receitas vs Despesas{(' em ' + str(year)) if year else ''}",
            xaxis_title="Mês",
            yaxis_title="Valor (R$)",
            yaxis_tickformat=",.2f"
        )
        st.plotly_chart(fig, use_container_width=True, key="monthly_comparison_chart")

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar dados de comparação mensal: {e}")
    except Exception as e:
        st.error(f"Erro ao processar dados do gráfico de comparação mensal: {e}")