import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# Importações dos componentes existentes e novos
from components import (
    monthly_summary_component,
    total_balance_component,
    balance_evolution_component,
    expenses_by_category_component,
    incomes_by_category_component,
    monthly_comparison_component,
    transactions_table_component,
    kpis_component
)
from settings import BACKEND_URL

st.set_page_config(layout="wide", page_title="Financial Dashboard")

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros Globais")

# Filtro de Data
today = datetime.now().date()
default_start_date = today - timedelta(days=30)

start_date_filter = st.sidebar.date_input("Data Inicial", default_start_date, key="home_start_date")
end_date_filter = st.sidebar.date_input("Data Final", today, key="home_end_date")

if start_date_filter > end_date_filter:
    st.sidebar.error("Data inicial não pode ser maior que a data final.")
    # Bloqueia a execução do restante se as datas forem inválidas
    st.stop()

# Placeholder para filtro de conta (account_id)
# Você precisaria de um endpoint para listar contas e popular este selectbox
# mock_accounts = {None: "Todas as Contas", 1: "Conta Principal", 2: "Cartão de Crédito X"}
# selected_account_id_filter = st.sidebar.selectbox(
# "Selecionar Conta:",
# options=list(mock_accounts.keys()),
# format_func=lambda x: mock_accounts[x],
# key="home_account_id"
# )
selected_account_id_filter = None # Sem filtro de conta por enquanto

# --- TÍTULO PRINCIPAL ---
title_cols = st.columns((1,2,1)) # Ajuste para centralizar melhor
with title_cols[1]:
    st.title('Financial Dashboard :moneybag:')

st.divider()

# --- DADOS INICIAIS DA HOME (Resumo Mensal e Saldo Total) ---
# Esta chamada busca os dados para os componentes originais
try:
    home_data_response = requests.get(f"{BACKEND_URL}/dashboard/home")
    home_data_response.raise_for_status()
    home_data = home_data_response.json()
except requests.exceptions.RequestException as e:
    st.error(f"Não foi possível carregar os dados iniciais do dashboard: {e}")
    home_data = {"month_balance": {"income": 0.0, "outcome": 0.0}, "total_balance": 0.0} # Dados padrão em caso de erro

summary_cols = st.columns(((2,1))) # Ajuste de proporção

with summary_cols[0]:
    st.subheader("Balanço dos Últimos 30 Dias")
    monthly_summary_component.generate_pie_chart(
        home_data['month_balance'].get('income', 0.0),
        home_data['month_balance'].get('outcome', 0.0)
    )
        
with summary_cols[1]:
    st.subheader("Saldo Geral Atual")
    total_balance_component.get_total_balance(
        home_data.get('total_balance', 0.0),
        home_data.get('month_balance', {"income": 0.0, "outcome": 0.0})
    )

st.divider()

# --- SEÇÃO DE KPIs ---
st.header("Indicadores Chave de Performance (KPIs)")
kpis_component.display_kpis(start_date_filter, end_date_filter, selected_account_id_filter)

st.divider()

# --- SEÇÃO DE GRÁFICOS DETALHADOS ---
st.header("Análises Detalhadas")

# --- Evolução do Saldo ---
with st.expander("Evolução do Saldo no Período", expanded=True):
    balance_evolution_component.generate_balance_evolution_chart(
        start_date=start_date_filter,
        end_date=end_date_filter,
        account_id=selected_account_id_filter
    )

# --- Despesas e Receitas por Categoria ---
with st.expander("Distribuição por Categoria no Período", expanded=True):
    col_cat_expense, col_cat_income = st.columns(2)
    with col_cat_expense:
        expenses_by_category_component.generate_expenses_pie_chart(
            start_date=start_date_filter,
            end_date=end_date_filter,
            account_id=selected_account_id_filter
        )
    with col_cat_income:
        incomes_by_category_component.generate_incomes_pie_chart(
            start_date=start_date_filter,
            end_date=end_date_filter,
            account_id=selected_account_id_filter
        )

# --- Comparativo Mensal (Receitas x Despesas) ---
with st.expander("Comparativo Mensal (Receitas x Despesas)", expanded=False):
    current_year = datetime.now().year
    # Gera uma lista de anos, por exemplo, dos últimos 5 anos até o atual.
    year_options = list(range(current_year - 4, current_year + 1))
    # Define o índice padrão para o ano atual.
    default_year_index = year_options.index(current_year) if current_year in year_options else len(year_options) -1

    selected_year_monthly_comp = st.selectbox(
        "Selecione o Ano:",
        options=year_options,
        index=default_year_index, # Ano atual como padrão
        key="home_monthly_comp_year"
    )
    monthly_comparison_component.generate_monthly_comparison_bar_chart(
        year=selected_year_monthly_comp,
        account_id=selected_account_id_filter
    )

st.divider()

# --- SEÇÃO DE TABELA DE TRANSAÇÕES ---
st.header("Histórico de Transações")

# Filtros específicos para a tabela de transações
tran_filter_cols = st.columns((2,1,1))
with tran_filter_cols[0]:
    tran_cat_filter = st.text_input("Buscar na Descrição/Categoria:", key="home_trans_cat_search")
with tran_filter_cols[1]:
    tran_type_options = {None: "Todos", "income": "Receita", "outcome": "Despesa"}
    selected_tran_type = st.selectbox(
        "Tipo:",
        options=list(tran_type_options.keys()),
        format_func=lambda x: tran_type_options[x],
        key="home_trans_type"
    )

# Paginação para a tabela de transações
if 'current_page_transactions_home' not in st.session_state:
    st.session_state.current_page_transactions_home = 1

limit_transactions_home = 15 # Número de transações por página

# Exibe a tabela
df_transactions_home = transactions_table_component.display_transactions_table(
    start_date=start_date_filter,
    end_date=end_date_filter,
    transaction_type=selected_tran_type,
    category=tran_cat_filter if tran_cat_filter else None, # Usa a busca para categoria/descrição
    account_id=selected_account_id_filter,
    limit=limit_transactions_home,
    page=st.session_state.current_page_transactions_home
)

# Controles de Paginação
page_cols = st.columns((1,1,1,3)) # Adicionado um spacer
with page_cols[0]:
    if st.session_state.current_page_transactions_home > 1:
        if st.button("⬅️ Anterior", key="home_prev_page_trans"):
            st.session_state.current_page_transactions_home -= 1
            st.rerun()
with page_cols[1]:
    st.write(f"Página {st.session_state.current_page_transactions_home}")

with page_cols[2]:
    # Para saber se existe próxima página, o ideal seria ter o total de transações.
    # Como heurística: se o dataframe retornado tiver o número máximo de itens, presume-se que há mais.
    if df_transactions_home is not None and not df_transactions_home.empty and len(df_transactions_home) == limit_transactions_home:
        if st.button("Próxima ➡️", key="home_next_page_trans"):
            st.session_state.current_page_transactions_home += 1
            st.rerun()
    elif df_transactions_home is not None and len(df_transactions_home) < limit_transactions_home and st.session_state.current_page_transactions_home > 1:
        # Se não há mais itens e não estamos na primeira página, não mostra o botão "Próxima"
        pass
    elif df_transactions_home is not None and df_transactions_home.empty and st.session_state.current_page_transactions_home == 1:
         # Se a primeira página está vazia, não mostra o botão "Próxima"
        pass