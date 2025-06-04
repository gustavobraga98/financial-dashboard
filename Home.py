import streamlit as st
from components import monthly_summary_component, total_balance_component
import requests
from settings import BACKEND_URL

st.set_page_config(layout="wide")
title_cols = st.columns((1,1,1))
with title_cols[1]:
    st.title('Financial Dashboard :moneybag:')

summary_cols = st.columns(((4,1)))

home_data = requests.get(f"{BACKEND_URL}/dashboard/home").json()

with summary_cols[0]:
    monthly_summary_component.generate_pie_chart(home_data['month_balance']['income'],
                                                  home_data['month_balance']['outcome'])

        
with summary_cols[1]:
    total_balance_component.get_total_balance(home_data['total_balance'], home_data['month_balance'])