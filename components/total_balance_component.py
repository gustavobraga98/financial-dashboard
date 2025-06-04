from settings import BACKEND_URL
import requests
import streamlit as st

def get_total_balance(total_balance: float = 0.0, month_balance: dict = {"income": 0.0, "outcome": 0.0}):
    """
    Retrieves the total balance from the backend service.
    
    Returns:
        float: The total balance.
    """
    variation = month_balance.get("income", 0.0) - month_balance.get("outcome", 0.0)
    return st.metric(label="Balance", value=f"{total_balance:.2f} R$", delta=f"{variation:.2f} R$")
