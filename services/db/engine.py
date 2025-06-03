from sqlalchemy import create_engine
from settings import PG_USER, PG_PASSWORD, PG_HOST, PG_PORT, PG_DATABASE

# Create the SQLAlchemy engine
engine = create_engine(f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}")