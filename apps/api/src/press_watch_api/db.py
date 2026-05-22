from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from press_watch_api.config import load_settings


settings = load_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
