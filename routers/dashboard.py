from fastapi import APIRouter
from handlers import get_total_balance_handler, get_month_balance_handler

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@dashboard_router.get("/home")
async def get_home():
    """
    Endpoint to retrieve the home dashboard.
    """
    month_balance = get_month_balance_handler.execute()
    total_balance = get_total_balance_handler.execute()
    return {
        "month_balance": month_balance,
        "total_balance": total_balance
    }
