import plotly.graph_objects as go
import requests
from settings import BACKEND_URL
import streamlit as st

import plotly.graph_objects as go
import streamlit as st

def generate_pie_chart(income, outcome):
    """
    Generates a pie chart showing the distribution of income and outcome.
    Income is represented in green and outcome in red.

    Parameters:
    income (float): The total income amount.
    outcome (float): The total outcome amount.
    """

    # Ensure income and outcome are numeric, default to 0 if not (or handle error appropriately)
    try:
        income_value = float(income)
        outcome_value = float(outcome)
    except (ValueError, TypeError):
        # If conversion fails, create a chart with an error message
        fig = go.Figure()
        fig.add_annotation(text="Invalid input: Income and Outcome must be numeric.", 
                           showarrow=False, font=dict(size=16))
        return st.plotly_chart(fig, use_container_width=True, key="monthly_summary_pie_chart_error")

    labels = ["Income", "Outcome"]
    # Use the validated numeric values
    values = [income_value, outcome_value]
    
    # Define colors for the slices
    colors = ['#28a745', '#dc3545'] # Green for Income, Red for Outcome

    # Create the pie chart
    fig = go.Figure(data=[go.Pie(
        labels=labels, 
        values=values,
        marker_colors=colors, # Apply custom colors
        name='' # Setting name to empty to avoid "trace 0" in hover
    )])
    
    # Update traces for styling
    fig.update_traces(
        hole=.7, 
        hoverinfo="label+percent+value", # Show label, percent, and the actual value
        textinfo='percent+label', # Show percent and label on the pie slices
    )
    
    # Update layout for a cleaner look
    fig.update_layout(
        title_text='Monthly Balance: Income vs Outcome',
        title_x=0.5, # Center the title
        legend_title_text='Categories',
        # annotations=[dict(text='Balance', x=0.5, y=0.5, font_size=20, showarrow=False)] # Optional: text in the middle of the donut
    )
    
    return st.plotly_chart(fig, use_container_width=True, key="monthly_summary_pie_chart")