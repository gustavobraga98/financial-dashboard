import streamlit as st

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a more premium look
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    h1 {
        color: #2c3e50;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
    }
    .stButton>button {
        border-radius: 8px;
        background-color: #4a90e2;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #357abd;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.title("💰 Dashboard Financeiro")
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(label="Saldo Atual", value="R$ 0,00", delta="0,00%")
    
    with col2:
        st.metric(label="Receitas (Mês)", value="R$ 0,00", delta="0,00%")
        
    with col3:
        st.metric(label="Despesas (Mês)", value="R$ 0,00", delta="0,00%")

    st.markdown("---")
    st.info("Bem-vindo ao seu novo dashboard financeiro! Comece adicionando suas transações.")

if __name__ == "__main__":
    main()
