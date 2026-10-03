import pytest

from app.core.exceptions import ExternalDataError
from app.services import session_catalog


@pytest.mark.asyncio
async def test_uncached_catalogue_request_does_not_require_access_token(monkeypatch):
    request = {}

    class Response:
        status_code = 200

        def json(self):
            return []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, *, params, headers):
            request.update(url=url, params=params, headers=headers)
            return Response()

    monkeypatch.setattr(session_catalog.httpx, "AsyncClient", Client)
    service = session_catalog.SessionCatalogService()

    assert await service._get_openf1("meetings", {"year": 2026}) == []
    assert request["headers"] == {"accept": "application/json"}


@pytest.mark.asyncio
async def test_catalogue_uses_durable_records_when_openf1_is_unavailable(monkeypatch):
    fallback = {
        "year": 2026,
        "meetings": [{"meeting_key": 42, "sessions": []}],
    }

    async def unavailable(*_args, **_kwargs):
        raise ExternalDataError("OpenF1 meetings returned 401", status_code=401)

    async def database_catalogue(_year):
        return fallback

    service = session_catalog.SessionCatalogService()
    monkeypatch.setattr(service, "_load_cache", lambda _year: None)
    monkeypatch.setattr(service, "_get_openf1", unavailable)
    monkeypatch.setattr(service, "_database_catalogue", database_catalogue)

    assert await service.year_catalogue(2026) == fallback
