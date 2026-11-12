"""Великі відповіді: не тримати все тіло в пам'яті і мати стелю розміру."""
import asyncio
import resource
import time

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()
LIMIT = 5 * 1024 * 1024                        # 5 МБ — більше нам не потрібно


def peak_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024   # Linux: КБ → МБ


print(f"пам'ять процесу на старті: {peak_mb()} МБ")

start = time.perf_counter()
total = 0
with requests.get(f"{BASE}/big", params={"mb": 50}, stream=True, timeout=5) as response:
    for chunk in response.iter_content(chunk_size=64 * 1024):
        total += len(chunk)                     # тут — запис у файл або парсинг частинами
print(f"requests stream=True: {total // 2**20} МБ частинами за {time.perf_counter() - start:.1f} с, "
      f"пік пам'яті {peak_mb()} МБ")

total = 0
with httpx.Client() as client, client.stream("GET", f"{BASE}/big", params={"mb": 50}) as response:
    for chunk in response.iter_bytes():
        total += len(chunk)
print(f"httpx client.stream: {total // 2**20} МБ, пік пам'яті {peak_mb()} МБ")


async def read_limited(url: str, max_bytes: int) -> bytes:
    """Як у safe_fetch: читаємо частинами і зупиняємось на стелі, навіть без Content-Length."""
    async with aiohttp.ClientSession() as session, session.get(url) as resp:
        print("aiohttp: Content-Length =", resp.content_length)
        body = bytearray()
        async for chunk in resp.content.iter_chunked(64 * 1024):
            body += chunk
            if len(body) > max_bytes:
                raise ValueError(f"відповідь більша за {max_bytes} байт — далі не читаємо")
        return bytes(body)

try:
    asyncio.run(read_limited(f"{BASE}/big?mb=50", LIMIT))
except ValueError as error:
    print("aiohttp:", error)

response = requests.get(f"{BASE}/big", params={"mb": 200}, timeout=5)   # без stream: усе тіло в пам'ять
print(f"requests без stream, 200 МБ: len(content) = {len(response.content) // 2**20} МБ, "
      f"пік пам'яті {peak_mb()} МБ")
