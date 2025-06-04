from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import pandas as pd
from io import StringIO
from typing import Optional
from handlers import pdf_to_markdown, markdown_to_csv, process_csv, register_df
import uvicorn
from pydantic import BaseModel, UUID4
from models import User, Bank, Account, Transaction
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from decimal import Decimal

from services.db.session import get_db

database_router = APIRouter(prefix="/database", tags=["Database"])

@database_router.post("/process_file/")
async def process_file(
    account_id: int,
    file: UploadFile = File(...),
    separator: Optional[str] = Form(","),  # <--- Aceita como parte do formulário
    db: Session = Depends(get_db),
):
    contents = await file.read()

    if file.content_type == "database_routerlication/pdf":
        markdown = pdf_to_markdown.execute(
            pdf_to_markdown.ProcessPdfModel(pdf_binary=contents)
        )
        csv = markdown_to_csv.execute(
            markdown_to_csv.MarkdownToCsvModel(markdown=markdown)
        )
        df = pd.read_csv(StringIO(csv), sep=separator)

    elif file.content_type in ["text/csv", "database_routerlication/vnd.ms-excel", "text/plain"]:
        df = process_csv.execute(
            process_csv.ProcessCSVModel(
                csv_content=contents.decode("utf-8"), separator=separator
            )
        )
    else:
        raise HTTPException(status_code=400, detail="File type not supported")
    register_df.execute(register_df.RegisterDFModel(df=df, account_id=account_id))
    

class NewUser(BaseModel):
    name: str
    email: str


@database_router.post("/add_user")
async def add_user(payload: NewUser, db: Session = Depends(get_db)):
    user = User(name=payload.name, email=payload.email)

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email já cadastrado.")

    return {"message": "User added successfully", "user_id": str(user.id)}


class NewBank(BaseModel):
    name: str


@database_router.post("/create_bank")
async def create_bank(payload: NewBank, db: Session = Depends(get_db)):
    bank = Bank(name=payload.name)

    try:
        db.add(bank)
        db.commit()
        db.refresh(bank)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bank name already exists.")

    return {"message": "Bank created successfully", "bank_name": str(bank.name)}


class NewAccount(BaseModel):
    bank_id: int
    user_id: UUID4
    nickname: Optional[str] = None
    account_number: Optional[str] = None


@database_router.post("/create_account")
async def create_account(payload: NewAccount, db: Session = Depends(get_db)):
    bank = db.query(Bank).filter(Bank.id == payload.bank_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    account = Account(
        bank_id=bank.id,
        number=payload.account_number,
        user_id=payload.user_id,
        nickname=payload.nickname,
    )

    try:
        db.add(account)
        db.commit()
        db.refresh(account)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Account created successfully", "account_id": str(account.id)}


class NewTransaction(BaseModel):
    account_id: int
    amount: Decimal
    description: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD format
    category: Optional[str] = None


@database_router.post("/create_transaction")
async def create_transaction(payload: NewTransaction, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == payload.account_id).first()
    last_transaction = (
        db.query(Transaction)
        .filter(Transaction.account_id == payload.account_id)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .first()
    )

    if payload.category:
        payload.category = payload.category.capitalize()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    transaction = Transaction(
        account_id=account.id,
        amount=payload.amount,
        description=payload.description,
        date=payload.date,
        type="input" if payload.amount > 0 else "output",
        balance=(
            last_transaction.balance + payload.amount
            if last_transaction
            else payload.amount
        ),
        category=payload.category,  # You can set a default category or leave it as None
    )

    try:
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Transaction could not be created.")

    return {
        "message": "Transaction created successfully",
        "transaction_id": str(transaction.id),
    }


if __name__ == "__main__":
    uvicorn.run(database_router, host="0.0.0.0", port=8000)
