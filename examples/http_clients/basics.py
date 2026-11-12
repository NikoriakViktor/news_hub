"""Той самий GET трьома бібліотеками: статус, JSON, raise_for_status, User-Agent за замовчуванням."""
import asyncio

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()

print("--- requests (синхронний)")
response = requests.get(f"{BASE}/news", timeout=5)
print(response.status_code, response.headers["content-type"], response.json())
missing = requests.get(f"{BASE}/news/42", timeout=5)
print("404 без винятку:", missing.status_code, missing.ok, missing.json())
try:
    missing.raise_for_status()
except requests.HTTPError as error:
    print("raise_for_status →", type(error).__name__, "—", error)
print("User-Agent:", requests.get(f"{BASE}/echo", timeout=5).json()["user_agent"])
response = requests.get(f"{BASE}/echo", params={"district": "Поділ", "limit": 5}, timeout=5)
print("params= →", response.url)
prepared = requests.Request("POST", f"{BASE}/orders", json={"title": "Привіт"}).prepare()
print("json= →", prepared.headers["Content-Type"], prepared.headers["Content-Length"], prepared.body)

print("--- httpx.Client (синхронний)")
with httpx.Client(base_url=BASE) as client:
    response = client.get("/news")
    print(response.status_code, response.http_version, response.json())
    try:
        client.get("/news/42").raise_for_status()
    except httpx.HTTPStatusError as error:
        print("raise_for_status →", type(error).__name__, error.response.status_code, error.response.json())
    print("User-Agent:", client.get("/echo").json()["user_agent"])
    built = client.build_request("POST", "/orders", json={"title": "Привіт"})
    print("json= →", built.headers["content-type"], built.headers["content-length"], built.content)


async def with_async_clients() -> None:
    print("--- httpx.AsyncClient")
    async with httpx.AsyncClient(base_url=BASE) as client:
        response = await client.get("/news")
        print(response.status_code, response.json())

    print("--- aiohttp.ClientSession")
    async with aiohttp.ClientSession(base_url=BASE) as session:
        async with session.get("/news") as resp:          # відповідь — контекстний менеджер
            print(resp.status, resp.content_type, await resp.json())   # тіло читаємо через await
        async with session.get("/news/42") as resp:
            try:
                resp.raise_for_status()
            except aiohttp.ClientResponseError as error:
                print("raise_for_status →", type(error).__name__, error.status, error.message)
        async with session.get("/echo") as resp:
            print("User-Agent:", (await resp.json())["user_agent"])


asyncio.run(with_async_clients())
