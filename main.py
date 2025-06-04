from fastapi import FastAPI
from routers import database_router, dashboard_router


app = FastAPI()
app.include_router(database_router)
app.include_router(dashboard_router)