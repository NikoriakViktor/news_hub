"""Пул з'єднань: новий клієнт на кожен запит = нове TCP-з'єднання; один клієнт = те саме з'єднання."""
import asyncio
import time

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()
N = 200

print("--- порт клієнта, який бачить сервер (новий порт = нове з'єднання)")
print("requests.get × 3:   ", [requests.get(f"{BASE}/echo", timeout=5).json()["client_port"] for _ in range(3)])
with requests.Session() as session:
    print("Session × 3:        ", [session.get(f"{BASE}/echo", timeout=5).json()["client_port"] for _ in range(3)])
with httpx.Client(base_url=BASE) as client:
    print("httpx.Client × 3:   ", [client.get("/echo").json()["client_port"] for _ in range(3)])


async def aiohttp_ports() -> list[int]:
    async with aiohttp.ClientSession(base_url=BASE) as session:
        ports = []
        for _ in range(3):
            async with session.get("/echo") as resp:
                ports.append((await resp.json())["client_port"])
        return ports

print("aiohttp session × 3:", asyncio.run(aiohttp_ports()))

print(f"--- {N} запитів")
start = time.perf_counter()
for _ in range(N):
    requests.get(f"{BASE}/news", timeout=5)
print(f"{'requests.get щоразу:':<30} {time.perf_counter() - start:.2f} с")

start = time.perf_counter()
with requests.Session() as session:
    for _ in range(N):
        session.get(f"{BASE}/news", timeout=5)
print(f"{'одна requests.Session:':<30} {time.perf_counter() - start:.2f} с")

start = time.perf_counter()
for _ in range(N):
    with httpx.Client() as client:                 # так не треба: клієнт на кожен запит
        client.get(f"{BASE}/news")
print(f"{'httpx.Client на кожен запит:':<30} {time.perf_counter() - start:.2f} с")

start = time.perf_counter()
with httpx.Client(base_url=BASE) as client:
    for _ in range(N):
        client.get("/news")
print(f"{'один httpx.Client:':<30} {time.perf_counter() - start:.2f} с")
