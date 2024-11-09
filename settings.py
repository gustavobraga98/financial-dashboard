from postgres.database import connect_to_database
from dotenv import load_dotenv
import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Acessar as variáveis de ambiente
host = os.getenv('DATABASE_HOST', 'localhost')
database = os.getenv('DATABASE_NAME', 'postgres')
user = os.getenv('DATABASE_USER', 'postgres')
password = os.getenv('DATABASE_PASSWORD', 'postgres')

logger.info(f"Conectando ao banco de dados: {host}, {database}, {user}")

# Conectar ao banco de dados e retornar engine, Base e SessionLocal
engine, SessionLocal = connect_to_database(host, database, user, password)

async def get_session() -> AsyncSession:
    session = SessionLocal()
    try:
        return session
    finally:
        await session.close()

