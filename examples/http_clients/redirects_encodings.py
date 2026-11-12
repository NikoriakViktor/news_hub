"""Перенаправлення (хто йде за ними сам) і тіло відповіді: bytes → str за charset."""
import asyncio

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()

print("--- 301 /old-news → /news")
response = requests.get(f"{BASE}/old-news", timeout=5)
print("requests:", response.status_code, response.url, "history:", [r.status_code for r in response.history])
response = httpx.get(f"{BASE}/old-news")
print("httpx:   ", response.status_code, "location:", response.headers["location"], "| next:", response.next_request.url)
response = httpx.get(f"{BASE}/old-news", follow_redirects=True)
print("httpx follow_redirects=True:", response.status_code, response.url, [r.status_code for r in response.history])


async def aiohttp_redirect() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE}/old-news") as resp:
            print("aiohttp: ", resp.status, resp.url, "history:", [r.status for r in resp.history])
        try:
            async with session.get(f"{BASE}/loop", max_redirects=5) as resp:
                pass
        except aiohttp.TooManyRedirects as error:
            print("aiohttp /loop:", type(error).__name__, len(error.history), "перенаправлень")

asyncio.run(aiohttp_redirect())
try:
    requests.get(f"{BASE}/loop", timeout=5)
except requests.TooManyRedirects as error:
    print("requests /loop:", type(error).__name__, "—", error)

print("--- тіло: bytes і str")
response = requests.get(f"{BASE}/cp1251", timeout=5)
print("content[:12]:", response.content[:12])
print("charset з заголовка:", response.encoding, "→", response.text)

response = requests.get(f"{BASE}/cp1251-silent", timeout=5)
print("без charset: requests.encoding =", response.encoding, "→", response.text)
print("  apparent_encoding =", response.apparent_encoding)
response.encoding = "cp1251"
print("  encoding = 'cp1251' →", response.text)

response = httpx.get(f"{BASE}/cp1251-silent")
print("без charset: httpx.encoding =", response.encoding, "→", response.text)

print("--- битий байт: сервер обіцяє UTF-8, а в тілі 0xff")
print("requests:", repr(requests.get(f"{BASE}/broken", timeout=5).text[-6:]))
print("httpx:   ", repr(httpx.get(f"{BASE}/broken").text[-6:]))


async def aiohttp_text() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE}/cp1251") as resp:
            print("aiohttp cp1251:", resp.charset, "→", await resp.text())
        async with session.get(f"{BASE}/broken") as resp:
            try:
                await resp.text()
            except UnicodeDecodeError as error:
                print("aiohttp broken: text() →", type(error).__name__, error.reason)
            print("aiohttp broken: text(errors='replace') →", repr((await resp.text(errors="replace"))[-6:]))

asyncio.run(aiohttp_text())
