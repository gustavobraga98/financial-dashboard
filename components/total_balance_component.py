from settings import BACKEND_URL
import requests
import streamlit as st

def get_total_balance(total_balance: float = 0.0, month_balance: dict = {"income": 0.0, "outcome": 0.0}):
    """
    Retrieves the total balance and formats it for display.
    
    Returns:
        streamlit.metric: A Streamlit metric component displaying the formatted balance.
    """
    variation = month_balance.get("income", 0.0) - month_balance.get("outcome", 0.0)
    
    # Format the numbers to Brazilian currency style
    formatted_total_balance = f"{total_balance:_.2f}".replace('.', ',').replace('_', '.')
    formatted_variation = f"{variation:_.2f}".replace('.', ',').replace('_', '.')
    
    return st.metric(label="Balance", 
                     value=f"{formatted_total_balance} R$", 
                     delta=f"{formatted_variation} R$")
