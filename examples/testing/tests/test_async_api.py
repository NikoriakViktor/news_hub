"""API через httpx.AsyncClient + ASGITransport: тест і застосунок в одному циклі подій."""
import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from newsapp.api import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def aclient() -> AsyncIterator[httpx.AsyncClient]:
    """ASGITransport lifespan не запускає — запускаємо його самі."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_health(aclient: httpx.AsyncClient) -> None:
    assert (await aclient.get("/health")).json() == {"status": "ok"}


async def test_concurrent_requests_get_distinct_ids(aclient: httpx.AsyncClient) -> None:
    responses = await asyncio.gather(*(aclient.get("/health") for _ in range(20)))
    assert {r.status_code for r in responses} == {200}
    assert len({r.headers["X-Request-ID"] for r in responses}) == 20


async def test_lifespan_state_is_reachable_from_test(aclient: httpx.AsyncClient) -> None:
    assert (await aclient.post("/articles", json={"title": "Уряд ухвалив бюджет", "source": "rbc.ua"})).status_code == 201
    with app.state.session_factory() as session:                 # той самий engine, що в застосунку
        assert session.get_bind().dialect.name == "sqlite"
    assert (await aclient.get("/articles/уряд-ухвалив-бюджет")).status_code == 200
