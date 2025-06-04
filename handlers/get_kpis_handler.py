from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from models import Transaction
from services.db.session import get_db
from typing import Optional, Dict, Any
from datetime import date, timedelta
from decimal import Decimal

def execute(
    db: Session,
    start_date_param: Optional[date] = None,
    end_date_param: Optional[date] = None,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    
    # Define default period if not provided (e.g., last 30 days)
    if end_date_param is None:
        end_date_param = date.today()
    if start_date_param is None:
        start_date_param = end_date_param - timedelta(days=29) # Default to 30 days period ending today

    # Base query for the period
    base_query_period = db.query(Transaction).filter(
        Transaction.date >= start_date_param,
        Transaction.date <= end_date_param
    )
    if account_id:
        base_query_period = base_query_period.filter(Transaction.account_id == account_id)

    # Average Daily Expense
    total_days_in_period = (end_date_param - start_date_param).days + 1
    sum_expenses_period = base_query_period.with_entities(func.sum(Transaction.amount)).filter(Transaction.type == 'outcome').scalar()
    
    avg_daily_expense = 0.0
    if sum_expenses_period is not None and total_days_in_period > 0:
        avg_daily_expense = float(abs(sum_expenses_period)) / total_days_in_period

    # Top Expense in Period
    top_expense_q = base_query_period.filter(Transaction.type == 'outcome').order_by(Transaction.amount.asc()).first() # outcome is negative
    top_expense_data = None
    if top_expense_q:
        top_expense_data = {
            "description": top_expense_q.description,
            "amount": float(abs(top_expense_q.amount)),
            "date": top_expense_q.date.isoformat()
        }

    # Top Income in Period
    top_income_q = base_query_period.filter(Transaction.type == 'income').order_by(Transaction.amount.desc()).first()
    top_income_data = None
    if top_income_q:
        top_income_data = {
            "description": top_income_q.description,
            "amount": float(top_income_q.amount),
            "date": top_income_q.date.isoformat()
        }
        
    # Total Income and Outcome for the period
    total_income_period = base_query_period.with_entities(func.sum(Transaction.amount)).filter(Transaction.type == 'income').scalar() or Decimal(0)
    total_outcome_period = base_query_period.with_entities(func.sum(Transaction.amount)).filter(Transaction.type == 'outcome').scalar() or Decimal(0)

    return {
        "period_start_date": start_date_param.isoformat(),
        "period_end_date": end_date_param.isoformat(),
        "average_daily_expense": round(avg_daily_expense, 2),
        "total_income_in_period": float(total_income_period),
        "total_outcome_in_period": float(abs(total_outcome_period)),
        "net_change_in_period": float(total_income_period + total_outcome_period), # outcome is negative
        "top_expense_in_period": top_expense_data,
        "top_income_in_period": top_income_data,
    }