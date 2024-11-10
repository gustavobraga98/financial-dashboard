from postgres.data_models.balance import Balance  # Ajuste o caminho conforme necessário
from routers.transactions.data_models.transaction_data_model import TransactionModel
from routers.transactions.handlers import register_category_handler, register_transaction_handler
from settings import get_session
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from settings import logger

router = APIRouter()

@router.post("/")
async def create_transaction(transaction: TransactionModel):
    """
    Receive a transaction and save it in the database
    """
    result = await register_transaction_handler.execute(transaction)
    logger.info(result)

    if result.sucess:
        return JSONResponse(content=result.message, status_code=200)

    else:
        return JSONResponse(content=result.message, status_code=500)