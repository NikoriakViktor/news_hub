"""Тайм-аути: «без тайм-ауту» = вічно; connect / read / total; read-тайм-аут — між байтами, а не на всю відповідь."""
import asyncio
import socket
import threading
import time

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()


def timed(label: str, call) -> None:
    start = time.perf_counter()
    try:
        result = call()
        outcome = f"відповідь {result}"
    except Exception as error:                     # демонстрація: показуємо будь-який виняток
        outcome = type(error).__name__
    print(f"{label:<44} {outcome:<28} за {time.perf_counter() - start:.1f} с")


print("--- без тайм-ауту")
done = threading.Event()
threading.Thread(target=lambda: (requests.get(f"{BASE}/slow", params={"delay": 30}), done.set()),
                 daemon=True).start()
print("requests.get(url) без timeout: через 3 с ще чекає?", not done.wait(3))
print("тайм-аути за замовчуванням: httpx", httpx.Client().timeout,
      "| aiohttp", aiohttp.client.DEFAULT_TIMEOUT)

print("--- сервер не відповідає (read)")
timed("requests timeout=1, /slow?delay=3",
      lambda: requests.get(f"{BASE}/slow", timeout=1).status_code)
timed("httpx за замовчуванням (5 с), /slow?delay=3",
      lambda: httpx.get(f"{BASE}/slow").status_code)
timed("httpx за замовчуванням (5 с), /slow?delay=8",
      lambda: httpx.get(f"{BASE}/slow", params={"delay": 8}).status_code)

print("--- немає кому відповісти (connect)")
timed("requests, закритий порт 8799",
      lambda: requests.get("http://127.0.0.1:8799/", timeout=1).status_code)
timed("httpx, закритий порт 8799",
      lambda: httpx.get("http://127.0.0.1:8799/", timeout=1).status_code)

# сервер, що слухає порт, але ніколи не приймає з'єднань: черга (backlog) переповнена → SYN без відповіді
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(0)
port = listener.getsockname()[1]
fillers = []
for _ in range(4):
    sock = socket.socket()
    sock.setblocking(False)
    sock.connect_ex(("127.0.0.1", port))
    fillers.append(sock)
timed("httpx connect=1, переповнена черга з'єднань",
      lambda: httpx.get(f"http://127.0.0.1:{port}/", timeout=httpx.Timeout(10, connect=1)).status_code)

print("--- тіло капає по байту раз на 0.5 с, 6 байтів (≈ 3 с)")
timed("requests timeout=1",
      lambda: len(requests.get(f"{BASE}/drip", timeout=1).content))
timed("httpx timeout=1",
      lambda: len(httpx.get(f"{BASE}/drip", timeout=1).content))


async def aiohttp_drip(timeout: aiohttp.ClientTimeout) -> int:
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{BASE}/drip") as resp:
            return len(await resp.read())

timed("aiohttp sock_read=1",
      lambda: asyncio.run(aiohttp_drip(aiohttp.ClientTimeout(sock_read=1))))
timed("aiohttp total=1",
      lambda: asyncio.run(aiohttp_drip(aiohttp.ClientTimeout(total=1))))


async def httpx_drip_total(seconds: float) -> int:
    """У httpx немає «total»: загальну стелю ставить asyncio.timeout навколо всього запиту."""
    async with httpx.AsyncClient(timeout=1) as client:
        async with asyncio.timeout(seconds):
            response = await client.get(f"{BASE}/drip")
            return len(response.content)

timed("httpx timeout=1 + asyncio.timeout(1)", lambda: asyncio.run(httpx_drip_total(1)))
