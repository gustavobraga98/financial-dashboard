from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
import app.models # Import all models so Base can detect them

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dashboard Financeiro API")

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Bem-vindo ao Dashboard Financeiro API", "status": "ok"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
