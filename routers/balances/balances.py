from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from postgres.data_models.balance import Balance
from routers.balances.data_models.balance_create_data_model import BalanceCreate
from settings import get_session
from datetime import datetime

router = APIRouter()

@router.post("/balances/", response_model=BalanceCreate)
async def create_balance(balance: BalanceCreate):
    """
    Create a new balance entry in the database.
    """
    try:
        session: AsyncSession = await get_session()

        # Verificar se já existe um saldo para a mesma data
        existing_balance = await session.execute(
            select(Balance).where(Balance.date == balance.date)
        )
        existing_balance = existing_balance.scalar()

        if existing_balance:
            raise HTTPException(status_code=400, detail="Balance already exists for this date.")

        # Criação do novo balance
        new_balance = Balance(
            date=balance.date,
            value=balance.value
        )

        session.add(new_balance)
        await session.commit()
        await session.refresh(new_balance)

        return BalanceCreate(date=new_balance.date, value=new_balance.value)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating balance: {e}")
