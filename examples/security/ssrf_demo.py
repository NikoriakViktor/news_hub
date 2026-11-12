"""SSRF: які адреси «внутрішні», чому denylist рядків не працює, DNS rebinding, сліпий SSRF.

python ssrf_demo.py — «внутрішній сервіс» — локальний aiohttp-сервер на 127.0.0.1; DNS підмінено фейковим
resolver; жодного запиту в інтернет (публічні адреси лише класифікуються, з'єднань до них немає).
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp
import httpx
from aiohttp import web
from aiohttp.abc import AbstractResolver, ResolveResult
from fastapi import FastAPI
from yarl import URL


def title(text: str) -> None:
    print(f"--- {text}")


def normalize(ip):
    return ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip


def is_public(address: str) -> bool:
    ip = normalize(ipaddress.ip_address(address))
    return ip.is_global and not ip.is_multicast


# ---------------------------------------------------------------------------
title("1. які адреси публічні: ipaddress")
for address in ("127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
                "::1", "fe80::1", "fd00::1", "::ffff:169.254.169.254", "64:ff9b::a9fe:a9fe", "93.184.215.14"):
    ip = ipaddress.ip_address(address)
    print(f"   {address:24} private={ip.is_private!s:5} global={ip.is_global!s:5} → публічна: {is_public(address)}")

# ---------------------------------------------------------------------------
title("2. denylist рядків проти getaddrinfo")
DENY = {"localhost", "127.0.0.1", "169.254.169.254", "::1"}


def naive_allowed(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host not in DENY and not host.startswith("127.")


for url in ("http://127.0.0.1/", "http://2130706433/", "http://0x7f.1/", "http://0177.0.0.1/",
            "http://[::ffff:127.0.0.1]/", "http://LOCALHOST./", "http://0/"):
    host = urlparse(url).hostname
    resolved = sorted({info[4][0] for info in socket.getaddrinfo(host, 80, proto=socket.IPPROTO_TCP)})
    print(f"   {url:28} denylist пропускає: {naive_allowed(url)!s:5} → з'єднання з {resolved}")

# ---------------------------------------------------------------------------
title("3. два парсери — два різні хости")
for url in ("http://evil.example@127.0.0.1/", "http://127.0.0.1#@evil.example/", "http://127.0.0.1\\@evil.example/"):
    hosts = {"urlparse": urlparse(url).hostname, "httpx": httpx.URL(url).host}
    try:
        hosts["yarl"] = URL(url).host
    except ValueError as error:
        hosts["yarl"] = f"ValueError: {error}"[:40]
    print(f"   {url:34} {hosts}")


# ---------------------------------------------------------------------------
class FakeDNS(AbstractResolver):
    """DNS атакувальника: перша відповідь — публічна адреса, далі — 127.0.0.1 (TTL 0)."""

    def __init__(self, answers: list[str]) -> None:
        self.answers, self.calls = answers, 0

    async def resolve(self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
                      ) -> list[ResolveResult]:
        address = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return [ResolveResult(hostname=host, host=address, port=port, family=socket.AF_INET, proto=0,
                              flags=socket.AI_NUMERICHOST)]

    async def close(self) -> None:
        pass


class Blocked(ValueError):
    """Не OSError: aiohttp загортає OSError з resolver у ClientConnectorDNSError — і «заборонено» стало б «DNS-збоєм»."""


class CheckingResolver(AbstractResolver):
    """Перевірка там, де з'єднання бере адресу: що перевірили — до того й під'єднались."""

    def __init__(self, inner: AbstractResolver) -> None:
        self.inner = inner

    async def resolve(self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
                      ) -> list[ResolveResult]:
        results = await self.inner.resolve(host, port, family)
        for result in results:
            if not is_public(result["host"]):
                raise Blocked(f"{host} → {result['host']}: не публічна адреса")
        return results

    async def close(self) -> None:
        pass


async def main() -> None:
    hits: list[str] = []

    async def metadata(request: web.Request) -> web.Response:
        hits.append(request.path)
        return web.Response(text="INTERNAL: aws_secret_access_key=...")

    internal = web.Application()
    internal.router.add_get("/{tail:.*}", metadata)
    runner = web.AppRunner(internal)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    url = f"http://rebind.attacker.test:{port}/latest/meta-data/"

    # -----------------------------------------------------------------------
    title("4. DNS rebinding: перевірили одну адресу, під'єдналися до іншої")
    dns = FakeDNS(["93.184.215.14", "127.0.0.1"])
    checked = [r["host"] for r in await dns.resolve("rebind.attacker.test", port)]
    print(f"   перевірка: rebind.attacker.test → {checked} публічна: {all(map(is_public, checked))}")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=dns, use_dns_cache=False)) as session:
        async with session.get(url) as resp:
            print(f"   запит: {resp.status} {await resp.text()!r} | звернень до DNS: {dns.calls}, до внутрішнього: {len(hits)}")

    dns = FakeDNS(["93.184.215.14", "127.0.0.1"])
    await dns.resolve("rebind.attacker.test", port)                      # та сама перевірка «заздалегідь» пройшла
    connector = aiohttp.TCPConnector(resolver=CheckingResolver(dns), use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            await session.get(url)
        except Blocked as error:
            print(f"   перевірка в resolver з'єднання: Blocked — {error} | до внутрішнього: {len(hits)}")

    # -----------------------------------------------------------------------
    title("5. сліпий SSRF: тіла не видно, але текст помилки сканує порти")
    app = FastAPI()

    @app.get("/preview")
    async def preview(url: str) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(url)
            return {"result": f"HTTP {response.status_code}"}                 # тіло не віддаємо…
        except httpx.HTTPError as error:
            return {"result": type(error).__name__}                          # …але причину відмови — так

    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()                                                            # порт, на якому ніхто не слухає
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as api:
        for probe in (port, closed_port):
            r = await api.get("/preview", params={"url": f"http://127.0.0.1:{probe}/"})
            print(f"   /preview?url=http://127.0.0.1:<порт {'сервісу' if probe == port else 'без сервісу'}>/ → {r.json()}")
    print("   звернень до внутрішнього сервісу:", len(hits))
    await runner.cleanup()


asyncio.run(main())
