from contextlib import asynccontextmanager
from fastapi import FastAPI
from routers.home import home
from routers.transactions import transactions
from routers.categories import categories
from settings import engine, SessionLocal  # Renomeado de session para SessionLocal
from settings import logger
import uvicorn

app = FastAPI(debug=True)

app.include_router(home.router, prefix="/home", tags=["Home"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(categories.router, prefix="/categories", tags=["Categories"])

@app.get("/health-check")
async def health_check():
    return {"message": "Alive"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
