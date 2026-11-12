"""BFF (Backend for Frontend): один запит клієнта — три запити до сервісів.

    python bff/bff_demo.py

Три «сервіси» — окремі FastAPI-застосунки, але в одному процесі: httpx.ASGITransport передає
запит застосунку напряму, без мережі. Затримки сервісів імітують мережу й базу. Порівнюємо:
1) послідовні виклики, 2) asyncio.gather, 3) gather + тайм-аут і запасна відповідь,
коли один сервіс повільний, 4) що буде без тайм-ауту.
"""
import asyncio
import time
from typing import Any

import httpx
from fastapi import FastAPI

DELAY = {"users": 0.30, "orders": 0.40, "recs": 0.25}      # секунди, змінює сценарій 3


def make_service(name: str, payload: dict[str, Any]) -> FastAPI:
    service = FastAPI(title=name)

    @service.get("/{user_id}")
    async def handler(user_id: int) -> dict[str, Any]:
        await asyncio.sleep(DELAY[name])
        return {"user_id": user_id, **payload}

    return service


SERVICES = {
    "users": make_service("users", {"name": "Олена"}),
    "orders": make_service("orders", {"orders": [101, 102]}),
    "recs": make_service("recs", {"recommended": ["новини дня"]}),
}


def client(name: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=SERVICES[name]), base_url=f"http://{name}")


async def fetch(name: str, user_id: int) -> dict[str, Any]:
    async with client(name) as c:
        response = await c.get(f"/{user_id}")
        response.raise_for_status()
        return response.json()


async def sequential(user_id: int) -> dict[str, Any]:
    return {name: await fetch(name, user_id) for name in SERVICES}


async def parallel(user_id: int) -> dict[str, Any]:
    users, orders, recs = await asyncio.gather(*(fetch(n, user_id) for n in SERVICES))
    return {"users": users, "orders": orders, "recs": recs}


async def with_fallback(name: str, user_id: int, timeout: float, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        async with asyncio.timeout(timeout):
            return await fetch(name, user_id)
    except TimeoutError:
        return {**fallback, "degraded": True}


async def resilient(user_id: int) -> dict[str, Any]:
    users, orders, recs = await asyncio.gather(
        fetch("users", user_id),                                    # без користувача сторінки немає
        fetch("orders", user_id),
        with_fallback("recs", user_id, timeout=0.5, fallback={"recommended": []}),   # необов'язкове
    )
    return {"users": users, "orders": orders, "recs": recs}


# BFF — теж FastAPI-застосунок: фронтенд робить ОДИН запит
bff = FastAPI(title="bff")


@bff.get("/dashboard/{user_id}")
async def dashboard(user_id: int) -> dict[str, Any]:
    return await resilient(user_id)


async def timed(label: str, coro: Any) -> Any:
    start = time.perf_counter()
    result = await coro
    print(f"{label:<44} {time.perf_counter() - start:.2f} с")
    return result


async def main() -> None:
    print("затримки сервісів:", DELAY)
    await timed("1. послідовно (сума затримок)", sequential(1))
    await timed("2. asyncio.gather (найповільніший)", parallel(1))

    DELAY["recs"] = 5.0
    print("\nсервіс recs «завис»: відповідає за 5 с")
    result = await timed("3. gather + тайм-аут 0.5 с для recs", resilient(1))
    print("   recs:", result["recs"])
    await timed("4. gather без тайм-ауту", parallel(1))

    DELAY["recs"] = 0.25
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=bff), base_url="http://bff") as c:
        response = await timed("\nBFF: GET /dashboard/7 (один запит клієнта)", c.get("/dashboard/7"))
    print("  ", response.status_code, response.json())


if __name__ == "__main__":
    asyncio.run(main())
