import streamlit as st
import requests
import plotly.express as px
import pandas as pd
from settings import BACKEND_URL
from datetime import date
from typing import Optional

def generate_balance_evolution_chart(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
):
    """
    Generates and displays a line chart of balance evolution over time.
    """
    params = {}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if account_id:
        params["account_id"] = account_id

    try:
        response = requests.get(f"{BACKEND_URL}/dashboard/balance_evolution", params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        if not data:
            st.info("Não há dados de evolução de saldo para o período ou filtros selecionados.")
            return

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df['balance'] = df['balance'].astype(float)

        fig = px.line(df, x='date', y='balance', title="Evolução do Saldo", markers=True)
        fig.update_layout(
            xaxis_title="Data",
            yaxis_title="Saldo (R$)",
            yaxis_tickformat=",.2f"
        )
        st.plotly_chart(fig, use_container_width=True, key="balance_evolution_chart")

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar dados de evolução do saldo: {e}")
    except Exception as e:
        st.error(f"Erro ao processar dados do gráfico de evolução do saldo: {e}")