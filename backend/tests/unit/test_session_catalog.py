import pytest

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
