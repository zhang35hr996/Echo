from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from echo.config import settings
from echo.models import Base

engine = create_engine(f"sqlite:///{settings.db_path}", future=True)
SessionLocal = sessionmaker(bind=engine, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
