# database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Tuple
import logging
from postgres.data_models.balance import Balance
from postgres.data_models.general_base import Base

logger = logging.getLogger("uvicorn")


def connect_to_database(host: str, database: str, user: str, password: str) -> Tuple[AsyncEngine, sessionmaker]:
    DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}/{database}"

    engine = create_async_engine(DATABASE_URL, echo=True)

    SessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    return engine, SessionLocal

async def create_tables(engine: AsyncEngine):
    logger.info("Criando as tabelas no banco de dados")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tabelas criadas com sucesso")

