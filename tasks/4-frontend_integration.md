# Frontend Integration Task

Connect the Streamlit frontend to the FastAPI backend and build the user interface. The user interface must be slick, modern and useful. It should display graphs, statistics and other information that could be useful to the user. It should contain KPIs and charts. 

## Objectives
- **Backend Communication**: Create a client service (`api_client.py`) to handle requests to the FastAPI backend using `httpx` or `requests`.
- **Transaction Forms**: Build intuitive forms to register new entries:
    - Support for both standard Account transactions and Credit Card purchases.
    - Input fields for description, amount, category, date, and type (Income/Expense).
- **Transaction History**: Implement a dynamic table to display recent activity:
    - Columns: Data, Descrição, Categoria, Valor, and Tipo.
    - Use conditional formatting to highlight income (green) and expenses (red).
    - Include basic filtering (e.g., filter by month or category).
- **Key Performance Indicators (KPIs)**: Display summary cards with high-level metrics:
    - Saldo Total (Current Balance).
    - Total de Receitas (Month-to-date Income).
    - Total de Despesas (Month-to-date Expenses).
- **Financial Visualization**: Implement interactive charts:
    - "Evolução do Saldo" (Balance over time) using line charts.
    - "Gastos por Categoria" (Spending by category) using pie or donut charts.
- **Localization**: Ensure the entire UI is in Portuguese (pt-BR) and follows the project's clean/modern aesthetic.

