from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create the database engine with connection health checks
engine = create_engine(settings.POSTGRES_CONNECTION_URL, pool_pre_ping=True)

# Session factory for creating DB sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
