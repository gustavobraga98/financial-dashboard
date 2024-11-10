from fastapi import APIRouter
from routers.home import handlers as home_handlers
router = APIRouter()

@router.get("/balance_history/")
async def get_balance(range: str):
    balance = await home_handlers.get_balance_by_range_handler.execute(range)
    return balance


@router.get("/monthly-expenses/")
async def get_monthly_expenses():
    expenses = await home_handlers.get_monthly_expenses_handler.execute()
    return expenses

@router.get("/balance/")
async def get_total_balance():
    balance = await home_handlers.get_total_balance_handler.execute()
    return balance