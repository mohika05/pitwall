from app.core.config import Settings


def test_hosted_postgres_urls_are_normalized_for_asyncpg():
    settings = Settings(
        database_url="postgresql://pitwall:secret@example.test/pitwall?sslmode=require"
    )

    assert settings.database_url == (
        "postgresql+asyncpg://pitwall:secret@example.test/pitwall?ssl=require"
    )
