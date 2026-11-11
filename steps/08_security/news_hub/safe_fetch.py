"""Завантаження за чужим URL без SSRF (Server-Side Request Forgery). Урок 46.

Адмін додає RSS-джерело за адресою (`POST /api/sources`), а сервер її завантажує. Сервер стоїть **усередині**
мережі: бачить localhost, Redis, базу, внутрішні сервіси й адресу метаданих хмари 169.254.169.254, до яких
ззовні не дістатись. URL «http://169.254.169.254/latest/meta-data/» — прохання до сервера сходити туди
від свого імені (OWASP Top 10, A10).

Основа — розділ A10 `OWASP_TOP_10.md`:
перевірка `urlparse(url).hostname in ALLOWED_HOSTS_FOR_FETCH`, потім `requests.get(url)`.
Рефакторинг уроку 46 — перевіряється не **рядок** URL, а **адреса, куди йде з'єднання**:
- схема лише http/https, порт лише 80/443, без логіна й пароля в URL;
- ім'я хоста → IP через DNS; якщо **будь-яка** з адрес не публічна (loopback, приватна мережа, link-local
  з метаданими хмари, 0.0.0.0, multicast, зарезервована, IPv4 всередині IPv6) — відмова;
- перевіряє сам resolver з'єднання (`PolicyResolver`): aiohttp під'єднується саме до перевіреної адреси,
  тож DNS не встигне «передумати» між перевіркою і запитом (DNS rebinding);
- перенаправлення — вручну, кожне знову через ті самі перевірки; не більше трьох;
- тайм-аут, стеля розміру (читаємо частинами), лише XML-типи вмісту.
"""
import asyncio
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field

import aiohttp
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from yarl import URL

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
FEED_CONTENT_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml")
HEADERS = {"User-Agent": "news_hub/0.46 (+навчальний агрегатор новин)", "Accept": ", ".join(FEED_CONTENT_TYPES)}


class UnsafeURL(ValueError):
    """Адреса, куди сервер не піде: не та схема чи порт, або не публічна IP."""


class FetchError(Exception):
    """Адреса дозволена, але завантажити не вдалося: HTTP-помилка, розмір, тип, тайм-аут."""


def normalize(ip: IPAddress) -> IPAddress:
    """::ffff:127.0.0.1 — це 127.0.0.1: перевіряємо IPv4 всередині IPv6."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_public_ip(ip: IPAddress) -> bool:
    """is_global: не приватна, не loopback, не link-local, не 0.0.0.0, не зарезервована, не 100.64/10."""
    ip = normalize(ip)
    return ip.is_global and not ip.is_multicast


def describe(ip: IPAddress) -> str:
    ip = normalize(ip)
    for name, flag in (("loopback", ip.is_loopback), ("link-local", ip.is_link_local),
                       ("0.0.0.0 — «цей хост»", ip.is_unspecified), ("multicast", ip.is_multicast),
                       ("приватна мережа", ip.is_private), ("зарезервована", ip.is_reserved)):
        if flag:
            return name
    return "не публічна"


@dataclass(frozen=True)
class FetchPolicy:
    """Що дозволено. За замовчуванням — лише публічний інтернет; тести звужують чи розширюють явно."""
    allow_ip: Callable[[IPAddress], bool] = is_public_ip
    allowed_ports: frozenset[int] = frozenset({80, 443})
    max_redirects: int = 3
    max_bytes: int = 2_000_000
    timeout: float = 10.0
    content_types: tuple[str, ...] = FEED_CONTENT_TYPES


DEFAULT_POLICY = FetchPolicy()


def check_ip(address: str, policy: FetchPolicy) -> None:
    ip = normalize(ipaddress.ip_address(address.split("%")[0]))      # fe80::1%eth0 → fe80::1
    if not policy.allow_ip(ip):
        raise UnsafeURL(f"адреса {ip} — {describe(ip)}: сервер туди не звертається")


def check_url(url: str | URL, policy: FetchPolicy = DEFAULT_POLICY) -> URL:
    """Перевірки, для яких не потрібен DNS. Повертає розібраний URL."""
    parsed = URL(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL(f"схема {parsed.scheme or '(немає)'}: дозволено лише http і https")
    if not parsed.host:
        raise UnsafeURL("в адресі немає хоста")
    if parsed.user or parsed.password:
        raise UnsafeURL("логін і пароль в адресі не дозволено")
    if parsed.port not in policy.allowed_ports:
        raise UnsafeURL(f"порт {parsed.port}: дозволено {sorted(policy.allowed_ports)}")
    try:
        literal = ipaddress.ip_address(parsed.host)
    except ValueError:
        return parsed                    # ім'я хоста — перевірить resolver після DNS
    check_ip(str(literal), policy)       # IP в адресі aiohttp не резолвить — перевіряємо тут
    return parsed


class PolicyResolver(ThreadedResolver):
    """DNS + перевірка: aiohttp під'єднується лише до адрес, які повернув цей resolver."""

    def __init__(self, policy: FetchPolicy) -> None:
        super().__init__()
        self._policy = policy

    async def resolve(self, host: str, port: int = 0,
                      family: socket.AddressFamily = socket.AF_INET) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:           # «2130706433», «0x7f.1», «localhost» — getaddrinfo дає 127.0.0.1
            check_ip(result["host"], self._policy)
        return results


@dataclass
class FetchResult:
    url: str                             # остання адреса — після перенаправлень
    content_type: str
    body: bytes
    redirects: int
    charset: str | None = None
    chain: list[str] = field(default_factory=list)

    def text(self) -> str:
        return self.body.decode(self.charset or "utf-8", errors="replace")


async def _read_limited(resp: aiohttp.ClientResponse, max_bytes: int) -> bytes:
    if resp.content_length is not None and resp.content_length > max_bytes:
        raise FetchError(f"відповідь {resp.content_length} байт — більше за {max_bytes}")
    body = bytearray()
    async for chunk in resp.content.iter_chunked(64 * 1024):        # Content-Length може й не бути
        body += chunk
        if len(body) > max_bytes:
            raise FetchError(f"відповідь більша за {max_bytes} байт")
    return bytes(body)


async def safe_fetch(url: str, policy: FetchPolicy = DEFAULT_POLICY) -> FetchResult:
    """GET чужої адреси з усіма перевірками. UnsafeURL — адреса заборонена; FetchError — не вдалося."""
    current = check_url(url, policy)
    chain = [str(current)]
    connector = aiohttp.TCPConnector(resolver=PolicyResolver(policy), use_dns_cache=False)
    timeout = aiohttp.ClientTimeout(total=policy.timeout)
    # trust_env=False: без HTTP_PROXY з середовища — інакше з'єднання йшло б через проксі, повз наш resolver
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
        for redirects in range(policy.max_redirects + 1):
            try:
                async with session.get(current, headers=HEADERS, allow_redirects=False) as resp:
                    if resp.status in REDIRECT_STATUSES:
                        location = resp.headers.get("Location")
                        if not location:
                            raise FetchError(f"HTTP {resp.status} без Location")
                        current = check_url(current.join(URL(location)), policy)
                        chain.append(str(current))
                        continue
                    if resp.status != 200:
                        raise FetchError(f"HTTP {resp.status}")
                    if resp.content_type not in policy.content_types:
                        raise FetchError(f"тип вмісту {resp.content_type}: очікуємо RSS/XML")
                    body = await _read_limited(resp, policy.max_bytes)
                    return FetchResult(url=str(current), content_type=resp.content_type, body=body,
                                       redirects=redirects, charset=resp.charset, chain=chain)
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:   # у 3.10 це ще не TimeoutError
                raise FetchError(f"{type(error).__name__}: {error}") from error
    raise FetchError(f"більше {policy.max_redirects} перенаправлень")

