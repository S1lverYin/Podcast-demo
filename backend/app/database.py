from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create database tables and required storage directories."""
    from app import models  # noqa: F401

    settings.storage_path.mkdir(parents=True, exist_ok=True)
    for name in ("uploads", "downloads", "audio", "exports"):
        (settings.storage_path / name).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Apply tiny additive migrations for SQLite development installs."""
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "transcript_segments" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("transcript_segments")}
    with engine.begin() as connection:
        if "translated_text" not in columns:
            connection.execute(text("ALTER TABLE transcript_segments ADD COLUMN translated_text TEXT"))
