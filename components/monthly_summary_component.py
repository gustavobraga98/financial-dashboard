import plotly.graph_objects as go
import streamlit as st

def generate_pie_chart(income, outcome):
    """
    Generates a pie chart showing the distribution of income and outcome.
    Income is represented in green and outcome in red.
    The income percentage is displayed in the center of the donut hole.

    Parameters:
    income (float): The total income amount.
    outcome (float): The total outcome amount.
    """
    try:
        income_value = float(income)
        outcome_value = float(outcome)
    except (ValueError, TypeError):
        # If conversion fails, display an error message
        fig = go.Figure()
        fig.add_annotation(text="Invalid input: Income and Outcome must be numeric.",
                           showarrow=False, font=dict(size=16))
        return st.plotly_chart(fig, use_container_width=True, key="monthly_summary_pie_chart_error")

    labels = ["Income", "Outcome"]
    values = [income_value, outcome_value]
    colors = ['#28a745', '#dc3545'] # Green for Income, Red for Outcome

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker_colors=colors,
        name='' # Avoids "trace 0" in hover if hover were enabled
    )])
    
    fig.update_traces(
        hole=.7,
        hoverinfo='none', # Hover text removed as requested
        textinfo='percent+label',
        insidetextorientation='radial'
    )
    
    # Calculate text for the center of the donut
    total_value = income_value + outcome_value
    if income_value == 0 and outcome_value == 0:
        center_text = "N/A"
    elif total_value == 0: 
        # This case implies income/outcome might be non-zero but sum to zero (e.g. 50 and -50)
        # or one is zero and the other is also zero (already handled above).
        # For typical non-negative income/outcome, this path (if not 0,0) indicates unusual data.
        # Defaulting to 0% if income is 0, or 100% if income is positive and outcome makes total 0.
        center_text = "0.0%" if income_value == 0 else f"{(income_value / 1.0 if income_value != 0 else 0.0):.1f}%" # Avoid division by zero if income is 0
    else:
        income_percentage = (income_value / total_value) * 100
        center_text = f"{income_percentage:.1f}%"
        
    fig.update_layout(
        title_text='Monthly Balance: Income vs Outcome',
        title_x=0.5, # Center the title
        legend_title_text='Categories',
        annotations=[dict(text=center_text, 
                          x=0.5, y=0.5, 
                          font_size=22, # Adjusted font size
                          showarrow=False,
                          align="center")]
    )
    
    return st.plotly_chart(fig, use_container_width=True, key="monthly_summary_pie_chart")