"""FastAPI dependencies backed by the application's canonical resources."""

from app.persistence.database import get_db_session

__all__ = ["get_db_session"]
