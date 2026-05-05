from fastapi import APIRouter

from app.api.endpoints import accounts, credits, transactions

api_router = APIRouter()
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(credits.router, prefix="/credits", tags=["credits"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
