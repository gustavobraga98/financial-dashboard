import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from api_client import ApiClient
from data_importer import parse_credit_csv, parse_debit_txt

# Initialize API Client
api = ApiClient()

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a premium, theme-aware look
st.markdown("""
    <style>
    /* Premium typography and spacing */
    .stApp {
        max-width: 1400px;
        margin: 0 auto;
    }
    
    /* KPI Cards styling */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.2s ease;
    }
    
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.1);
    }
    
    /* Modern Headers */
    h1, h2, h3 {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        white-space: pre-wrap;
        background-color: rgba(255, 255, 255, 0.03);
        border-radius: 8px 8px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_dashboard_data():
    transactions = api.get_transactions()
    credits = api.get_credits()
    accounts = api.get_accounts()
    
    # Merge all for history
    df_tx = pd.DataFrame(transactions)
    df_cr = pd.DataFrame(credits)
    
    # Ensure columns exist even if data is empty
    for col in ['account_id', 'description', 'amount', 'type', 'category', 'date']:
        if col not in df_tx.columns: df_tx[col] = None
    for col in ['card_alias', 'description', 'amount', 'type', 'category', 'date']:
        if col not in df_cr.columns: df_cr[col] = None

    if not df_tx.empty:
        df_tx['source'] = 'Conta'
        df_tx['date'] = pd.to_datetime(df_tx['date'])
    
    if not df_cr.empty:
        df_cr['source'] = 'Cartão'
        df_cr['date'] = pd.to_datetime(df_cr['date'])
        
    all_history = df_tx.copy()
    if not all_history.empty:
        all_history = all_history.sort_values('date', ascending=False)
        # Final column check for concatenation results
        if 'account_id' not in all_history.columns:
            all_history['account_id'] = None
            
    return df_tx, df_cr, all_history, accounts

def show_dashboard(df_tx, df_cr, all_history, accounts):
    st.subheader("📊 Visão Geral")
    
    # Calculate current balance retroactively (up to TODAY)
    total_initial = sum(acc['initial_balance'] for acc in accounts)
    
    # Use the most recent reference date for global/credit items
    global_ref_date = max(pd.to_datetime(acc['initial_balance_date']).date() for acc in accounts) if accounts else datetime.now().date()
    today_date = datetime.now().date()
    
    adjusted_income = 0
    adjusted_expense = 0
    
    if not all_history.empty:
        for _, tx in all_history.iterrows():
            if pd.isna(tx['date']): continue
            tx_date = tx['date'].date()
            
            acc = next((a for a in accounts if a['id'] == tx['account_id']), None)
            if acc:
                acc_ref_date = pd.to_datetime(acc['initial_balance_date']).date()
                if acc_ref_date < tx_date <= today_date:
                    if tx['type'] == 'income': adjusted_income += tx['amount']
                    else: adjusted_expense += tx['amount']

    current_balance = total_initial + adjusted_income - adjusted_expense
    
    col1, col2, col3 = st.columns(3)
    
    with col1: 
        st.metric("Saldo Total", format_currency(current_balance))
        with st.expander("Ver detalhes do cálculo"):
            st.write(f"Soma Saldo Inicial: {format_currency(total_initial)}")
            st.write(f"Receitas (pós-referência): {format_currency(adjusted_income)}")
            st.write(f"Despesas (pós-referência): {format_currency(adjusted_expense)}")
            st.write(f"Data Base Geral: {global_ref_date}")
            
    with col2: 
        # Only show income/expense from current month for clarity
        current_month = datetime.now().month
        m_income = all_history[(all_history['type'] == 'income') & (all_history['date'].dt.month == current_month)]['amount'].sum() if not all_history.empty else 0
        st.metric("Receitas (Mês)", format_currency(m_income))
        
    with col3:
        m_expense = all_history[(all_history['type'] == 'expense') & (all_history['date'].dt.month == current_month)]['amount'].sum() if not all_history.empty else 0
        st.metric("Despesas (Mês)", format_currency(m_expense), delta_color="inverse")

    st.markdown("---")

    # 2. Charts
    if not all_history.empty and not all_history['date'].isna().all():
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("📈 Evolução do Saldo")
            df_trend = all_history.dropna(subset=['date']).sort_values('date', ascending=False).copy()
            balances = []
            running_bal = current_balance
            for _, row in df_trend.iterrows():
                balances.append(running_bal)
                net = row['amount'] if row['type'] == 'income' else -row['amount']
                running_bal -= net
            df_trend['cum_balance'] = balances
            fig_line = px.line(df_trend.sort_values('date'), x='date', y='cum_balance')
            st.plotly_chart(fig_line, use_container_width=True)
        with c2:
            st.subheader("🍕 Gastos por Categoria")
            df_cat = all_history[all_history['type'] == 'expense'].groupby('category')['amount'].sum().reset_index()
            if not df_cat.empty:
                st.plotly_chart(px.pie(df_cat, values='amount', names='category', hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe), use_container_width=True)

    st.markdown("---")
    st.subheader("📜 Histórico de Transações")
    if not all_history.empty:
        display_df = all_history[['date', 'description', 'category', 'amount', 'type', 'source']].copy()
        display_df['date'] = display_df['date'].dt.strftime('%d/%m/%Y')
        st.dataframe(display_df, use_container_width=True, hide_index=True)

def show_accounts(accounts):
    st.subheader("🏦 Gerenciar Contas")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Criar Nova Conta")
        with st.form("new_account"):
            acc_name = st.text_input("Nome da Conta")
            acc_balance = st.number_input("Saldo Inicial", format="%.2f")
            acc_date = st.date_input("Data do Saldo Inicial", datetime.now())
            if st.form_submit_button("Adicionar Conta"):
                if acc_name:
                    api.create_account({"name": acc_name, "initial_balance": acc_balance, "initial_balance_date": acc_date.isoformat()})
                    st.success("Conta criada!")
                    st.rerun()

    with col2:
        st.markdown("### Contas Existentes")
        if accounts:
            for acc in accounts:
                with st.expander(f"{acc['name']} - {format_currency(acc['initial_balance'])}"):
                    st.write(f"Data de Referência: {pd.to_datetime(acc['initial_balance_date']).strftime('%d/%m/%Y')}")
                    if st.button(f"Excluir {acc['name']}", key=f"del_{acc['id']}"):
                        # Add delete logic in api_client if needed
                        st.warning("Funcionalidade de exclusão em breve.")
        else:
            st.info("Nenhuma conta cadastrada.")

def show_import():
    st.subheader("📄 Importar Dados")
    c1, c2 = st.columns(2)
    with c1:
        uploaded_debit = st.file_uploader("Extrato Débito (.txt)", type="txt")
        if uploaded_debit and st.button("Processar Débito"):
            txs = parse_debit_txt(uploaded_debit.read())
            api.bulk_create_transactions(txs)
            st.success("Importado!")
            st.rerun()
    with c2:
        uploaded_credit = st.file_uploader("Extrato Crédito (.csv)", type="csv")
        if uploaded_credit and st.button("Processar Crédito"):
            crs = parse_credit_csv(uploaded_credit.read())
            api.bulk_create_credits(crs)
            st.success("Importado!")
            st.rerun()

def main():
    # Ensure default account
    if not api.get_accounts():
        api.create_account({"name": "Principal", "initial_balance": 0.0, "initial_balance_date": datetime.now().isoformat()})

    df_tx, df_cr, all_history, accounts = get_dashboard_data()

    # Sidebar Navigation
    with st.sidebar:
        st.title("💰 Finanças")
        menu = st.radio("Menu", ["📊 Dashboard", "🏦 Contas", "📄 Importar"])
        st.markdown("---")
        st.subheader("➕ Novo Registro")
        with st.form("quick_entry"):
            q_desc = st.text_input("Descrição")
            q_amt = st.number_input("Valor", min_value=0.01)
            q_type = st.radio("Tipo", ["Despesa", "Receita"], horizontal=True)
            q_orig = st.selectbox("Origem", ["Conta", "Cartão"])
            if st.form_submit_button("Salvar"):
                tx_type = 'expense' if q_type == "Despesa" else 'income'
                if q_orig == "Conta":
                    api.create_transaction({"description": q_desc, "amount": q_amt, "type": tx_type, "category": "Outros", "date": datetime.now().isoformat(), "account_id": accounts[0]['id']})
                else:
                    api.create_credit({"description": q_desc, "amount": q_amt, "type": tx_type, "category": "Outros", "date": datetime.now().isoformat(), "card_alias": "Principal"})
                st.success("Salvo!")
                st.rerun()

    if menu == "📊 Dashboard": show_dashboard(df_tx, df_cr, all_history, accounts)
    elif menu == "🏦 Contas": show_accounts(accounts)
    elif menu == "📄 Importar": show_import()

if __name__ == "__main__":
    main()
