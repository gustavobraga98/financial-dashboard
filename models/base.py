from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from settings import PG_URL

Base = declarative_base()
engine = create_engine(PG_URL)