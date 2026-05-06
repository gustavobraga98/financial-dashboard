import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Any

def parse_credit_csv(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Parses credit.csv format: data,lançamento,valor
    - Separator: ,
    - Date: YYYY-MM-DD
    - Positive value = Expense, Negative = Payment (Income)
    """
    df = pd.read_csv(io.BytesIO(file_content))
    transactions = []
    
    for _, row in df.iterrows():
        # Clean description (remove installments like 02/02)
        desc = row['lançamento']
        val = float(row['valor'])
        
        tx_type = 'expense' if val > 0 else 'income'
        
        transactions.append({
            "description": desc,
            "amount": abs(val),
            "type": tx_type,
            "date": row['data'], # ISO format YYYY-MM-DD is accepted by FastAPI/Pydantic
            "card_alias": "Principal" # Default alias
        })
    return transactions

def parse_debit_txt(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Parses debit.txt format: DD/MM/YYYY;Description;Amount
    - Separator: ;
    - Date: DD/MM/YYYY
    - Negative value = Expense, Positive = Income
    - Decimal separator: ,
    """
    # Read as CSV with ; separator and no header
    df = pd.read_csv(
        io.BytesIO(file_content), 
        sep=';', 
        header=None, 
        names=['date', 'description', 'amount'],
        decimal=','
    )
    
    transactions = []
    for _, row in df.iterrows():
        val = float(row['amount'])
        tx_type = 'expense' if val < 0 else 'income'
        
        # Convert DD/MM/YYYY to YYYY-MM-DD
        dt = datetime.strptime(row['date'], '%d/%m/%Y').strftime('%Y-%m-%d')
        
        transactions.append({
            "description": row['description'],
            "amount": abs(val),
            "type": tx_type,
            "date": dt,
            "account_id": 1 # Default account
        })
    return transactions
