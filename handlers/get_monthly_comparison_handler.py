from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from models import Transaction
from services.db.session import get_db
from typing import Optional, List, Dict
from datetime import date
from decimal import Decimal

def execute(
    db: Session,
    year: Optional[int] = None,
    account_id: Optional[int] = None
) -> List[Dict[str, any]]:
    # Query for income
    income_query = (
        db.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total_income')
        )
        .filter(Transaction.type == 'income')
    )

    # Query for outcome
    outcome_query = (
        db.query(
            extract('year', Transaction.date).label('year'),
            extract('month', Transaction.date).label('month'),
            func.sum(Transaction.amount).label('total_outcome')
        )
        .filter(Transaction.type == 'outcome')
    )

    if account_id:
        income_query = income_query.filter(Transaction.account_id == account_id)
        outcome_query = outcome_query.filter(Transaction.account_id == account_id)

    if year:
        income_query = income_query.filter(extract('year', Transaction.date) == year)
        outcome_query = outcome_query.filter(extract('year', Transaction.date) == year)

    income_results = income_query.group_by('year', 'month').all()
    outcome_results = outcome_query.group_by('year', 'month').all()

    comparison_data = {}
    for r_income in income_results:
        month_year_key = f"{int(r_income.year)}-{int(r_income.month):02d}"
        if month_year_key not in comparison_data:
            comparison_data[month_year_key] = {"month": month_year_key, "income": 0.0, "outcome": 0.0}
        comparison_data[month_year_key]["income"] = float(r_income.total_income)

    for r_outcome in outcome_results:
        month_year_key = f"{int(r_outcome.year)}-{int(r_outcome.month):02d}"
        if month_year_key not in comparison_data:
            comparison_data[month_year_key] = {"month": month_year_key, "income": 0.0, "outcome": 0.0}
        # Outcomes are stored as negative, make them positive for comparison
        comparison_data[month_year_key]["outcome"] = float(abs(r_outcome.total_outcome))
    
    # Sort by month and convert to list
    sorted_comparison = sorted(comparison_data.values(), key=lambda x: x["month"])
    
    return sorted_comparison