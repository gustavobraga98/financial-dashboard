from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.db.session import get_db
from typing import Optional, List, Dict, Any
from datetime import date

from handlers import (
    get_total_balance_handler,
    get_month_balance_handler,
    get_balance_evolution_handler,
    get_expenses_by_category_handler,
    get_incomes_by_category_handler,
    get_monthly_comparison_handler,
    get_transactions_handler,
    get_kpis_handler
)

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@dashboard_router.get("/home")
async def get_home_data(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve the home dashboard summary.
    """
    # Pass the db session to the handlers
    month_balance_data = get_month_balance_handler.execute(db=db) # Pass db session
    total_balance_data = get_total_balance_handler.execute(db=db) # Pass db session

    return {
        "month_balance": month_balance_data,
        "total_balance": total_balance_data
    }

@dashboard_router.get("/balance_evolution", response_model=List[Dict[str, Any]])
async def get_balance_evolution_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_balance_evolution_handler.execute(
        db=db, start_date=start_date, end_date=end_date, account_id=account_id
    )

@dashboard_router.get("/expenses_by_category", response_model=List[Dict[str, Any]])
async def get_expenses_by_category_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_expenses_by_category_handler.execute(
        db=db, start_date=start_date, end_date=end_date, account_id=account_id
    )

@dashboard_router.get("/incomes_by_category", response_model=List[Dict[str, Any]])
async def get_incomes_by_category_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_incomes_by_category_handler.execute(
        db=db, start_date=start_date, end_date=end_date, account_id=account_id
    )

@dashboard_router.get("/monthly_comparison", response_model=List[Dict[str, Any]])
async def get_monthly_comparison_data(
    year: Optional[int] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_monthly_comparison_handler.execute(db=db, year=year, account_id=account_id)

@dashboard_router.get("/transactions", response_model=List[Dict[str, Any]])
async def get_transactions_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    transaction_type: Optional[str] = None,
    category: Optional[str] = None,
    account_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return get_transactions_handler.execute(
        db=db,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
        limit=limit,
        offset=offset
    )

@dashboard_router.get("/kpis", response_model=Dict[str, Any])
async def get_kpis_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    return get_kpis_handler.execute(
        db=db, start_date_param=start_date, end_date_param=end_date, account_id=account_id
    )