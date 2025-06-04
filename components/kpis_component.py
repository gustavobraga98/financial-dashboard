import streamlit as st
import requests
from settings import BACKEND_URL # Make sure this setting is correctly configured
from datetime import date
from typing import Optional
import pandas as pd

def display_kpis(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
):
    """
    Displays Key Performance Indicators (KPIs) for the selected period.
    """
    params = {}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if account_id:
        params["account_id"] = account_id

    try:
        response = requests.get(f"{BACKEND_URL}/dashboard/kpis", params=params)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        kpis = response.json()

        if not kpis:
            st.info("Não foi possível calcular os KPIs para o período ou filtros selecionados.")
            return

        # Format period dates for the subheader
        raw_period_start = kpis.get('period_start_date')
        raw_period_end = kpis.get('period_end_date')
        
        formatted_period_start = pd.to_datetime(raw_period_start).strftime('%d/%m/%Y') if raw_period_start else 'N/A'
        formatted_period_end = pd.to_datetime(raw_period_end).strftime('%d/%m/%Y') if raw_period_end else 'N/A'
        
        st.subheader(f"Indicadores Chave de Performance ({formatted_period_start} a {formatted_period_end})")
        
        cols = st.columns(3)
        
        with cols[0]:
            avg_daily_expense_raw = kpis.get('average_daily_expense')
            avg_daily_expense = float(avg_daily_expense_raw) if avg_daily_expense_raw is not None else 0.0
            st.metric(
                label="Média de Gasto Diário",
                value=f"R$ {avg_daily_expense:_.2f}".replace('.', ',').replace('_', '.')
            )
            
        with cols[1]:
            total_income_raw = kpis.get('total_income_in_period')
            total_income = float(total_income_raw) if total_income_raw is not None else 0.0
            st.metric(
                label="Total de Receitas no Período",
                value=f"R$ {total_income:_.2f}".replace('.', ',').replace('_', '.')
            )
            
        with cols[2]:
            total_outcome_raw = kpis.get('total_outcome_in_period')
            total_outcome = float(total_outcome_raw) if total_outcome_raw is not None else 0.0
            st.metric(
                label="Total de Despesas no Período",
                value=f"R$ {total_outcome:_.2f}".replace('.', ',').replace('_', '.')
            )
        
        net_change_raw = kpis.get('net_change_in_period')
        net_change = float(net_change_raw) if net_change_raw is not None else 0.0
        
        delta_color = "normal"
        if net_change < 0:
            delta_color = "inverse"

        st.metric(
            label="Saldo do Período (Receitas - Despesas)",
            value=f"R$ {net_change:_.2f}".replace('.', ',').replace('_', '.'),
            delta_color=delta_color 
        )

        top_expense_data = kpis.get('top_expense_in_period')
        if top_expense_data:
            top_expense_desc = top_expense_data.get('description', 'N/A')
            
            top_expense_amount_raw = top_expense_data.get('amount')
            top_expense_amount = float(top_expense_amount_raw) if top_expense_amount_raw is not None else 0.0
            # Pre-format the amount string for markdown
            formatted_top_expense_amount = f"R$ {top_expense_amount:_.2f}".replace('.', ',').replace('_', '.')
            
            top_expense_date_raw = top_expense_data.get('date')
            top_expense_date_formatted = pd.to_datetime(top_expense_date_raw).strftime('%d/%m/%Y') if top_expense_date_raw else 'N/A'
            
            st.markdown(f"""
            **Maior Despesa no Período:**
            - Descrição: {top_expense_desc}
            - Valor: {formatted_top_expense_amount}
            - Data: {top_expense_date_formatted}
            """)

        top_income_data = kpis.get('top_income_in_period')
        if top_income_data:
            top_income_desc = top_income_data.get('description', 'N/A')
            
            top_income_amount_raw = top_income_data.get('amount')
            top_income_amount = float(top_income_amount_raw) if top_income_amount_raw is not None else 0.0
            # Pre-format the amount string for markdown
            formatted_top_income_amount = f"R$ {top_income_amount:_.2f}".replace('.', ',').replace('_', '.')

            top_income_date_raw = top_income_data.get('date')
            top_income_date_formatted = pd.to_datetime(top_income_date_raw).strftime('%d/%m/%Y') if top_income_date_raw else 'N/A'

            st.markdown(f"""
            **Maior Receita no Período:**
            - Descrição: {top_income_desc}
            - Valor: {formatted_top_income_amount}
            - Data: {top_income_date_formatted}
            """)

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar KPIs: {e}")
    except Exception as e:
        st.error(f"Erro ao processar dados dos KPIs: {e}")